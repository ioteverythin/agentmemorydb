"""Tests for automatic memory linking.

Two failure modes matter more than the happy path: linking too much (which makes
graph traversal useless), and linking things that should not be reachable at all
(a path from a trusted memory into a quarantined one routes around quarantine).
Both get direct tests, as does the symmetry of ``related_to`` — the property that
stops every re-write from adding another copy of the same edge.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.memory import Memory
from app.models.memory_link import MemoryLink
from app.models.user import User
from app.schemas.memory import MemoryUpsert
from app.services.autolink_service import LINK_TYPE, AutolinkService
from app.services.memory_service import MemoryService


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "enable_autolink", True)


async def _user(session) -> uuid.UUID:
    uid = uuid.uuid4()
    session.add(User(id=uid, name="autolink-user"))
    await session.flush()
    return uid


_DEFAULT_VECTOR = object()  # distinguishes "not given" from an explicit None


def _mem(
    user_id,
    key,
    *,
    embedding=_DEFAULT_VECTOR,
    status="active",
    project_id=None,
    content=None,
) -> Memory:
    return Memory(
        id=uuid.uuid4(),
        user_id=user_id,
        memory_key=key,
        memory_type="semantic",
        layer="atom",
        project_id=project_id,
        content=content or f"content of {key}",
        content_hash=f"hash-{key}",
        status=status,
        embedding=[1.0, 0.0, 0.0] if embedding is _DEFAULT_VECTOR else embedding,
        confidence=0.7,
        importance_score=0.5,
        authority_level=1,
        recency_score=1.0,
        version=1,
    )


async def _links(session) -> list[MemoryLink]:
    return list(
        (await session.execute(select(MemoryLink).where(MemoryLink.link_type == LINK_TYPE)))
        .scalars()
        .all()
    )


# ── The gate ────────────────────────────────────────────────────


@pytest.mark.unit
class TestFeatureFlag:
    @pytest.mark.asyncio
    async def test_disabled_by_default(self, unit_session):
        assert settings.enable_autolink is False
        user_id = await _user(unit_session)
        neighbour = _mem(user_id, "a")
        subject = _mem(user_id, "b")
        unit_session.add_all([neighbour, subject])
        await unit_session.flush()

        assert await AutolinkService(unit_session).autolink(subject) == []
        assert await _links(unit_session) == []

    @pytest.mark.asyncio
    async def test_explicit_request_works_while_disabled(self, unit_session):
        """The flag governs automatic linking; an explicit call is a decision."""
        user_id = await _user(unit_session)
        unit_session.add_all([_mem(user_id, "a"), (subject := _mem(user_id, "b"))])
        await unit_session.flush()

        created = await AutolinkService(unit_session).autolink_now(subject)
        assert len(created) == 1

    @pytest.mark.asyncio
    async def test_memory_without_an_embedding_is_skipped(self, unit_session, enabled):
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "a"))
        subject = _mem(user_id, "b", embedding=None)
        unit_session.add(subject)
        await unit_session.flush()

        assert await AutolinkService(unit_session).autolink(subject) == []


# ── What gets linked ────────────────────────────────────────────


@pytest.mark.unit
class TestLinking:
    @pytest.mark.asyncio
    async def test_similar_memories_are_linked(self, unit_session, enabled):
        user_id = await _user(unit_session)
        neighbour = _mem(user_id, "neighbour")
        subject = _mem(user_id, "subject")
        unit_session.add_all([neighbour, subject])
        await unit_session.flush()

        created = await AutolinkService(unit_session).autolink(subject)
        assert len(created) == 1
        assert created[0].source_memory_id == subject.id
        assert created[0].target_memory_id == neighbour.id
        assert created[0].link_type == LINK_TYPE
        assert "similarity" in created[0].description

    @pytest.mark.asyncio
    async def test_dissimilar_memories_are_not_linked(self, unit_session, enabled):
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "far", embedding=[0.0, 1.0, 0.0]))
        subject = _mem(user_id, "subject", embedding=[1.0, 0.0, 0.0])
        unit_session.add(subject)
        await unit_session.flush()

        assert await AutolinkService(unit_session).autolink(subject) == []

    @pytest.mark.asyncio
    async def test_link_count_is_capped(self, unit_session, enabled, monkeypatch):
        """Linking everything to everything is the same as linking nothing."""
        monkeypatch.setattr(settings, "autolink_max_links", 2)
        user_id = await _user(unit_session)
        for i in range(5):
            unit_session.add(_mem(user_id, f"n{i}"))
        subject = _mem(user_id, "subject")
        unit_session.add(subject)
        await unit_session.flush()

        created = await AutolinkService(unit_session).autolink(subject)
        assert len(created) == 2

    @pytest.mark.asyncio
    async def test_never_links_to_itself(self, unit_session, enabled):
        user_id = await _user(unit_session)
        subject = _mem(user_id, "lonely")
        unit_session.add(subject)
        await unit_session.flush()

        assert await AutolinkService(unit_session).autolink(subject) == []

    @pytest.mark.asyncio
    async def test_never_crosses_users(self, unit_session, enabled):
        user_a = await _user(unit_session)
        user_b = await _user(unit_session)
        unit_session.add(_mem(user_a, "theirs"))
        subject = _mem(user_b, "mine")
        unit_session.add(subject)
        await unit_session.flush()

        assert await AutolinkService(unit_session).autolink(subject) == []

    @pytest.mark.asyncio
    async def test_never_crosses_projects(self, unit_session, enabled):
        """Projects kept deliberately apart must not be bridged by inference."""
        user_id = await _user(unit_session)
        project_a, project_b = uuid.uuid4(), uuid.uuid4()
        unit_session.add(_mem(user_id, "other-project", project_id=project_a))
        unit_session.add(_mem(user_id, "no-project"))
        subject = _mem(user_id, "subject", project_id=project_b)
        unit_session.add(subject)
        await unit_session.flush()

        assert await AutolinkService(unit_session).autolink(subject) == []


# ── Safety: what must never be linked ───────────────────────────


@pytest.mark.unit
class TestUnlinkableStatuses:
    @pytest.mark.asyncio
    async def test_quarantined_memories_are_never_a_target(self, unit_session, enabled):
        """A link into quarantine is a path that routes around it."""
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "poisoned", status="quarantined"))
        subject = _mem(user_id, "subject")
        unit_session.add(subject)
        await unit_session.flush()

        assert await AutolinkService(unit_session).autolink(subject) == []

    @pytest.mark.asyncio
    async def test_quarantined_memories_are_never_a_source(self, unit_session, enabled):
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "trusted"))
        subject = _mem(user_id, "poisoned", status="quarantined")
        unit_session.add(subject)
        await unit_session.flush()

        assert await AutolinkService(unit_session).autolink(subject) == []

    @pytest.mark.asyncio
    async def test_disputed_and_archived_are_excluded(self, unit_session, enabled):
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "disputed", status="disputed"))
        unit_session.add(_mem(user_id, "archived", status="archived"))
        subject = _mem(user_id, "subject")
        unit_session.add(subject)
        await unit_session.flush()

        assert await AutolinkService(unit_session).autolink(subject) == []


# ── Deduplication ───────────────────────────────────────────────


@pytest.mark.unit
class TestDeduplication:
    @pytest.mark.asyncio
    async def test_relinking_adds_nothing(self, unit_session, enabled):
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "neighbour"))
        subject = _mem(user_id, "subject")
        unit_session.add(subject)
        await unit_session.flush()

        svc = AutolinkService(unit_session)
        assert len(await svc.autolink(subject)) == 1
        assert await svc.autolink(subject) == []
        assert len(await _links(unit_session)) == 1

    @pytest.mark.asyncio
    async def test_reverse_edge_suppresses_a_new_one(self, unit_session, enabled):
        """``related_to`` is symmetric: B→A already covers A→B."""
        user_id = await _user(unit_session)
        neighbour = _mem(user_id, "neighbour")
        subject = _mem(user_id, "subject")
        unit_session.add_all([neighbour, subject])
        await unit_session.flush()

        svc = AutolinkService(unit_session)
        await svc.autolink(neighbour)  # neighbour → subject
        assert await svc.autolink(subject) == []  # subject → neighbour suppressed
        assert len(await _links(unit_session)) == 1

    @pytest.mark.asyncio
    async def test_other_link_types_do_not_block_autolinking(self, unit_session, enabled):
        """A `derived_from` edge says something different from `related_to`."""
        user_id = await _user(unit_session)
        neighbour = _mem(user_id, "neighbour")
        subject = _mem(user_id, "subject")
        unit_session.add_all([neighbour, subject])
        await unit_session.flush()
        unit_session.add(
            MemoryLink(
                source_memory_id=subject.id,
                target_memory_id=neighbour.id,
                link_type="derived_from",
            )
        )
        await unit_session.flush()

        assert len(await AutolinkService(unit_session).autolink(subject)) == 1


# ── Integration with the write path ─────────────────────────────


@pytest.mark.unit
class TestUpsertIntegration:
    @pytest.mark.asyncio
    async def test_upsert_links_a_new_memory(self, unit_session, enabled, monkeypatch):
        # The dummy provider hashes text into a vector, so two different texts
        # are not similar. Pin the threshold low enough that any pair links.
        monkeypatch.setattr(settings, "autolink_similarity_threshold", -1.0)
        user_id = await _user(unit_session)
        svc = MemoryService(unit_session)

        await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="fact:a",
                memory_type="semantic",
                content="Uses Postgres.",
            ),
            emit=False,
        )
        await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="fact:b",
                memory_type="semantic",
                content="Runs migrations nightly.",
            ),
            emit=False,
        )
        await unit_session.flush()

        assert len(await _links(unit_session)) == 1

    @pytest.mark.asyncio
    async def test_upsert_does_not_link_when_disabled(self, unit_session, monkeypatch):
        monkeypatch.setattr(settings, "autolink_similarity_threshold", -1.0)
        user_id = await _user(unit_session)
        svc = MemoryService(unit_session)
        for key in ("fact:a", "fact:b"):
            await svc.upsert(
                MemoryUpsert(
                    user_id=user_id,
                    memory_key=key,
                    memory_type="semantic",
                    content=f"content for {key}",
                ),
                emit=False,
            )
        await unit_session.flush()

        assert await _links(unit_session) == []

    @pytest.mark.asyncio
    async def test_quarantined_write_is_not_linked(self, unit_session, enabled, monkeypatch):
        monkeypatch.setattr(settings, "autolink_similarity_threshold", -1.0)
        monkeypatch.setattr(settings, "enable_poisoning_resistance", True)
        user_id = await _user(unit_session)
        svc = MemoryService(unit_session)

        await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="fact:trusted",
                memory_type="semantic",
                content="Something the user said.",
                origin="user",
            ),
            emit=False,
        )
        memory, _ = await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="fact:scraped",
                memory_type="semantic",
                content="Something a web page said.",
                origin="external_ingest",
                confidence=0.1,
            ),
            emit=False,
        )
        await unit_session.flush()

        assert memory.status == "quarantined"
        assert await _links(unit_session) == []


# ── Backfill ────────────────────────────────────────────────────


@pytest.mark.unit
class TestBackfill:
    @pytest.mark.asyncio
    async def test_backfill_links_existing_memories(self, unit_session, enabled):
        user_id = await _user(unit_session)
        for i in range(3):
            unit_session.add(_mem(user_id, f"n{i}"))
        await unit_session.flush()

        report = await AutolinkService(unit_session).backfill(user_id)
        assert report["memories_scanned"] == 3
        assert report["links_created"] > 0

    @pytest.mark.asyncio
    async def test_backfill_dry_run_writes_nothing(self, unit_session, enabled):
        user_id = await _user(unit_session)
        for i in range(3):
            unit_session.add(_mem(user_id, f"n{i}"))
        await unit_session.flush()

        report = await AutolinkService(unit_session).backfill(user_id, dry_run=True)
        assert report["dry_run"] is True
        assert report["links_created"] > 0
        assert await _links(unit_session) == []

    @pytest.mark.asyncio
    async def test_backfill_is_idempotent(self, unit_session, enabled):
        user_id = await _user(unit_session)
        for i in range(3):
            unit_session.add(_mem(user_id, f"n{i}"))
        await unit_session.flush()

        svc = AutolinkService(unit_session)
        first = await svc.backfill(user_id)
        second = await svc.backfill(user_id)
        assert first["links_created"] > 0
        assert second["links_created"] == 0
