"""Tests for auditable forgetting: decay, pinning, reconsolidation, erasure.

The invariant under test across all of these: nothing leaves active recall
silently. Decay, expiry, and erasure each leave a ``forgetting_log`` row, and
erasure keeps a content hash so the deletion is provable without the content.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.forgetting_log import ForgettingLog
from app.models.memory import Memory
from app.models.memory_access_log import MemoryAccessLog
from app.models.memory_version import MemoryVersion
from app.models.user import User
from app.schemas.memory import MemorySearchRequest, MemoryUpsert
from app.services.forgetting_service import ForgettingService
from app.services.memory_service import MemoryService
from app.services.retrieval_service import RetrievalService


async def _user(session) -> uuid.UUID:
    uid = uuid.uuid4()
    session.add(User(id=uid, name="decay-user"))
    await session.flush()
    return uid


def _mem(
    user_id,
    key,
    *,
    importance=0.5,
    age_days=0,
    pinned=False,
    layer="atom",
    status="active",
    expires_at=None,
) -> Memory:
    ts = datetime.now(UTC) - timedelta(days=age_days)
    return Memory(
        id=uuid.uuid4(),
        user_id=user_id,
        memory_key=key,
        memory_type="semantic",
        layer=layer,
        content=f"content of {key}",
        content_hash=f"hash-{key}",
        status=status,
        pinned=pinned,
        importance_score=importance,
        confidence=0.5,
        authority_level=1,
        recency_score=1.0,
        version=1,
        valid_from=ts,
        expires_at=expires_at,
        created_at=ts,
        updated_at=ts,
    )


async def _get(session, key) -> Memory:
    return (await session.execute(select(Memory).where(Memory.memory_key == key))).scalars().first()


async def _log_rows(session, *, action=None) -> list[ForgettingLog]:
    stmt = select(ForgettingLog)
    if action is not None:
        stmt = stmt.where(ForgettingLog.action == action)
    return list((await session.execute(stmt)).scalars().all())


# ── Importance decay ────────────────────────────────────────────


@pytest.mark.unit
class TestImportanceDecay:
    @pytest.mark.asyncio
    async def test_unused_memory_decays(self, unit_session):
        user_id = await _user(unit_session)
        # 30 days old with a 30-day half-life → importance should roughly halve.
        unit_session.add(_mem(user_id, "cold", importance=0.8, age_days=30))
        await unit_session.flush()

        report = await ForgettingService(unit_session).decay_importance()
        assert report["decayed"] == 1

        decayed = (await _get(unit_session, "cold")).importance_score
        assert decayed == pytest.approx(0.8 * 0.5, abs=0.02)

    @pytest.mark.asyncio
    async def test_decay_never_goes_below_floor(self, unit_session):
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "ancient", importance=0.6, age_days=3650))
        await unit_session.flush()

        await ForgettingService(unit_session).decay_importance()
        assert (await _get(unit_session, "ancient")).importance_score == settings.decay_floor

    @pytest.mark.asyncio
    async def test_pinned_memory_never_decays(self, unit_session):
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "pinned", importance=0.8, age_days=365, pinned=True))
        await unit_session.flush()

        report = await ForgettingService(unit_session).decay_importance()
        assert report["decayed"] == 0
        assert (await _get(unit_session, "pinned")).importance_score == 0.8

    @pytest.mark.asyncio
    async def test_recent_access_resists_decay(self, unit_session):
        """Recall — not age — is what keeps importance up."""
        user_id = await _user(unit_session)
        recalled = _mem(user_id, "recalled", importance=0.8, age_days=60)
        unit_session.add(recalled)
        await unit_session.flush()
        unit_session.add(MemoryAccessLog(memory_id=recalled.id, user_id=user_id))
        await unit_session.flush()

        await ForgettingService(unit_session).decay_importance()
        # Last activity is the access (just now), so decay is negligible.
        assert (await _get(unit_session, "recalled")).importance_score == pytest.approx(
            0.8, abs=0.01
        )

    @pytest.mark.asyncio
    async def test_dry_run_reports_without_writing(self, unit_session):
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "cold", importance=0.8, age_days=30))
        await unit_session.flush()

        report = await ForgettingService(unit_session).decay_importance(dry_run=True)
        assert report["decayed"] == 1
        assert (await _get(unit_session, "cold")).importance_score == 0.8

    @pytest.mark.asyncio
    async def test_archived_memories_are_not_decayed(self, unit_session):
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "gone", importance=0.8, age_days=90, status="archived"))
        await unit_session.flush()

        report = await ForgettingService(unit_session).decay_importance()
        assert report["considered"] == 0


# ── Pinning ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestPinning:
    @pytest.mark.asyncio
    async def test_pinned_memory_is_not_archived(self, unit_session):
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "keep", importance=0.05, age_days=180, pinned=True))
        await unit_session.flush()

        report = await ForgettingService(unit_session).archive_low_retention()
        assert report["archived"] == 0
        assert (await _get(unit_session, "keep")).status == "active"

    @pytest.mark.asyncio
    async def test_upsert_can_pin_and_pin_survives_content_update(self, unit_session):
        user_id = await _user(unit_session)
        svc = MemoryService(unit_session)
        memory, _ = await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="pref:home",
                memory_type="semantic",
                content="Lives in Pune.",
                pinned=True,
            ),
            emit=False,
        )
        assert memory.pinned is True

        # A later content update omits `pinned` — the pin must not be cleared.
        memory, _ = await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="pref:home",
                memory_type="semantic",
                content="Lives in Mumbai.",
            ),
            emit=False,
        )
        assert memory.pinned is True

    @pytest.mark.asyncio
    async def test_set_pinned_toggles(self, unit_session):
        user_id = await _user(unit_session)
        memory = _mem(user_id, "toggle")
        unit_session.add(memory)
        await unit_session.flush()

        svc = MemoryService(unit_session)
        assert (await svc.set_pinned(memory.id, pinned=True)).pinned is True
        assert (await svc.set_pinned(memory.id, pinned=False)).pinned is False


# ── Reconsolidation on retrieval ────────────────────────────────


@pytest.mark.unit
class TestReconsolidation:
    @pytest.mark.asyncio
    async def test_disabled_by_default(self, unit_session, monkeypatch):
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "recall-me", importance=0.5))
        await unit_session.flush()

        monkeypatch.setattr(settings, "enable_reconsolidation", False)
        await RetrievalService(unit_session).search(
            MemorySearchRequest(user_id=user_id, query_text="recall", top_k=5)
        )
        assert (await _get(unit_session, "recall-me")).importance_score == 0.5

    @pytest.mark.asyncio
    async def test_retrieval_boosts_importance(self, unit_session, monkeypatch):
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "recall-me", importance=0.5))
        await unit_session.flush()

        monkeypatch.setattr(settings, "enable_reconsolidation", True)
        await RetrievalService(unit_session).search(
            MemorySearchRequest(user_id=user_id, query_text="recall", top_k=5)
        )
        assert (await _get(unit_session, "recall-me")).importance_score == pytest.approx(
            0.5 + settings.reconsolidation_boost
        )

    @pytest.mark.asyncio
    async def test_boost_is_capped_at_one(self, unit_session, monkeypatch):
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "maxed", importance=0.999))
        await unit_session.flush()

        monkeypatch.setattr(settings, "enable_reconsolidation", True)
        await RetrievalService(unit_session).search(
            MemorySearchRequest(user_id=user_id, query_text="maxed", top_k=5)
        )
        assert (await _get(unit_session, "maxed")).importance_score == 1.0

    @pytest.mark.asyncio
    async def test_point_in_time_query_does_not_reinforce(self, unit_session, monkeypatch):
        """Auditing history must not rewrite it."""
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "historic", importance=0.5, age_days=10))
        await unit_session.flush()

        monkeypatch.setattr(settings, "enable_reconsolidation", True)
        await RetrievalService(unit_session).search(
            MemorySearchRequest(
                user_id=user_id,
                query_text="historic",
                top_k=5,
                as_of=datetime.now(UTC) - timedelta(days=5),
            )
        )
        assert (await _get(unit_session, "historic")).importance_score == 0.5


# ── Auditable erasure ───────────────────────────────────────────


@pytest.mark.unit
class TestErasure:
    @pytest.mark.asyncio
    async def test_erase_deletes_memory_and_versions_leaving_tombstone(self, unit_session):
        user_id = await _user(unit_session)
        memory = _mem(user_id, "secret")
        unit_session.add(memory)
        await unit_session.flush()
        unit_session.add(
            MemoryVersion(
                memory_id=memory.id,
                version=1,
                content="old secret",
                content_hash="hash-old",
                confidence=0.5,
                importance_score=0.5,
                source_type="system_inference",
                status="superseded",
            )
        )
        await unit_session.flush()
        original_hash = memory.content_hash

        report = await ForgettingService(unit_session).erase_memory(
            memory.id, reason="user requested deletion"
        )
        assert report["erased"] == 1

        assert await _get(unit_session, "secret") is None
        versions = (
            (
                await unit_session.execute(
                    select(MemoryVersion).where(MemoryVersion.memory_id == memory.id)
                )
            )
            .scalars()
            .all()
        )
        assert list(versions) == []

        rows = await _log_rows(unit_session, action="user_erasure")
        assert len(rows) == 1
        # The content is gone; the hash proves what was erased.
        assert rows[0].content_hash == original_hash
        assert rows[0].reason == "user requested deletion"
        assert rows[0].memory_id == memory.id

    @pytest.mark.asyncio
    async def test_tombstone_survives_the_erased_memory(self, unit_session):
        """The audit row has no FK to memories — it must outlive the row."""
        user_id = await _user(unit_session)
        memory = _mem(user_id, "gone")
        unit_session.add(memory)
        await unit_session.flush()

        await ForgettingService(unit_session).erase_memory(memory.id)
        await unit_session.commit()

        rows = await _log_rows(unit_session)
        assert [r.memory_id for r in rows] == [memory.id]

    @pytest.mark.asyncio
    async def test_erase_missing_memory_raises(self, unit_session):
        from app.core.errors import NotFoundError

        with pytest.raises(NotFoundError):
            await ForgettingService(unit_session).erase_memory(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_erase_all_user_memories(self, unit_session):
        user_id = await _user(unit_session)
        other_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "a"))
        unit_session.add(_mem(user_id, "b"))
        unit_session.add(_mem(other_id, "other"))
        await unit_session.flush()

        report = await ForgettingService(unit_session).erase_user_memories(user_id)
        assert report["erased"] == 2

        remaining = (await unit_session.execute(select(Memory))).scalars().all()
        assert [m.memory_key for m in remaining] == ["other"]
        assert len(await _log_rows(unit_session, action="user_erasure")) == 2


# ── Audit trail ─────────────────────────────────────────────────


@pytest.mark.unit
class TestForgettingLog:
    @pytest.mark.asyncio
    async def test_archival_is_logged(self, unit_session):
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "junk", importance=0.05, age_days=90))
        await unit_session.flush()

        await ForgettingService(unit_session).archive_low_retention()
        rows = await _log_rows(unit_session, action="decayed_archive")
        assert len(rows) == 1
        assert rows[0].triggered_by == "scheduler:archive_stale"
        assert rows[0].user_id == user_id

    @pytest.mark.asyncio
    async def test_dry_run_archival_is_not_logged(self, unit_session):
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "junk", importance=0.05, age_days=90))
        await unit_session.flush()

        await ForgettingService(unit_session).archive_low_retention(dry_run=True)
        assert await _log_rows(unit_session) == []

    @pytest.mark.asyncio
    async def test_expiry_retracts_and_logs(self, unit_session):
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "ttl", expires_at=datetime.now(UTC) - timedelta(hours=1)))
        unit_session.add(_mem(user_id, "future", expires_at=datetime.now(UTC) + timedelta(hours=1)))
        await unit_session.flush()

        report = await ForgettingService(unit_session).retract_expired()
        assert report["retracted_count"] == 1
        assert (await _get(unit_session, "ttl")).status == "retracted"
        assert (await _get(unit_session, "future")).status == "active"

        rows = await _log_rows(unit_session, action="expired")
        assert len(rows) == 1
        assert rows[0].triggered_by == "scheduler:cleanup_expired"

    @pytest.mark.asyncio
    async def test_list_log_filters_by_user(self, unit_session):
        user_id = await _user(unit_session)
        other_id = await _user(unit_session)
        mine = _mem(user_id, "mine")
        theirs = _mem(other_id, "theirs")
        unit_session.add_all([mine, theirs])
        await unit_session.flush()

        svc = ForgettingService(unit_session)
        await svc.erase_memory(mine.id)
        await svc.erase_memory(theirs.id)

        entries = await svc.list_log(user_id=user_id)
        assert [e.memory_id for e in entries] == [mine.id]
        assert len(await svc.list_log()) == 2
