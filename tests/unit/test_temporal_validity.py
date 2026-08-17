"""Tests for bitemporal fact validity: supersession, as-of queries, timeline."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.user import User
from app.schemas.memory import MemorySearchRequest, MemoryUpsert
from app.services.memory_service import MemoryService
from app.services.retrieval_service import RetrievalService
from app.services.temporal_service import TemporalService

# A fixed timeline so assertions read clearly.
T0 = datetime(2026, 1, 1, tzinfo=UTC)  # "lives in Mumbai"
T1 = datetime(2026, 3, 1, tzinfo=UTC)  # → Pune
T2 = datetime(2026, 6, 1, tzinfo=UTC)  # → Berlin


def ts(value: datetime | None) -> datetime | None:
    """Normalise to UTC-aware.

    The unit-test harness is SQLite, which has no timezone-aware type and
    round-trips datetimes naive. PostgreSQL (TIMESTAMPTZ) preserves the offset,
    so comparisons are normalised here rather than weakening the assertions.
    """
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


async def _user(session) -> uuid.UUID:
    uid = uuid.uuid4()
    session.add(User(id=uid, name="temporal-user"))
    await session.flush()
    return uid


async def _assert_city(svc, user_id, content, valid_from):
    mem, _ = await svc.upsert(
        MemoryUpsert(
            user_id=user_id,
            memory_key="fact:city",
            memory_type="semantic",
            content=content,
            valid_from=valid_from,
        )
    )
    return mem


@pytest.mark.unit
class TestSupersession:
    @pytest.mark.asyncio
    async def test_supersession_keeps_stable_id_and_closes_window(self, unit_session):
        user_id = await _user(unit_session)
        svc = MemoryService(unit_session)

        first = await _assert_city(svc, user_id, "Lives in Mumbai.", T0)
        first_id = first.id
        second = await _assert_city(svc, user_id, "Lives in Pune.", T1)

        # Canonical row keeps its identity (links/ACLs/client ids stay valid).
        assert second.id == first_id
        assert second.version == 2
        assert second.content == "Lives in Pune."
        # Current generation is open-ended and starts at the new valid_from.
        assert second.valid_to is None
        assert ts(second.valid_from) == T1

        # The prior generation is a closed window in the version chain.
        versions = await svc.get_versions(first_id)
        assert len(versions) == 1
        assert versions[0].content == "Lives in Mumbai."
        assert ts(versions[0].valid_from) == T0
        assert ts(versions[0].valid_to) == T1  # closes exactly where the next begins
        assert versions[0].status == "superseded"

    @pytest.mark.asyncio
    async def test_windows_tile_without_gaps_across_three_generations(self, unit_session):
        user_id = await _user(unit_session)
        svc = MemoryService(unit_session)
        await _assert_city(svc, user_id, "Lives in Mumbai.", T0)
        await _assert_city(svc, user_id, "Lives in Pune.", T1)
        current = await _assert_city(svc, user_id, "Lives in Berlin.", T2)

        versions = sorted(await svc.get_versions(current.id), key=lambda v: v.version)
        assert [v.content for v in versions] == ["Lives in Mumbai.", "Lives in Pune."]
        # Window N's end == window N+1's start; the last one is open.
        assert ts(versions[0].valid_to) == ts(versions[1].valid_from) == T1
        assert ts(versions[1].valid_to) == ts(current.valid_from) == T2
        assert current.valid_to is None

    @pytest.mark.asyncio
    async def test_backdated_valid_from(self, unit_session):
        """An agent may record a fact that became true in the past."""
        user_id = await _user(unit_session)
        svc = MemoryService(unit_session)
        await _assert_city(svc, user_id, "Lives in Mumbai.", T0)
        backdated = await _assert_city(svc, user_id, "Lives in Pune.", T1)

        assert ts(backdated.valid_from) == T1
        assert ts(backdated.valid_from) < datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_invalidate_only_closes_window_without_replacement(self, unit_session):
        user_id = await _user(unit_session)
        svc = MemoryService(unit_session)
        mem = await _assert_city(svc, user_id, "Lives in Mumbai.", T0)

        await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="fact:city",
                memory_type="semantic",
                content="(ignored)",
                valid_from=T1,
                invalidate_only=True,
            )
        )
        assert ts(mem.valid_to) == T1
        assert mem.status == "stale"
        # The final generation is preserved with its closed window.
        versions = await svc.get_versions(mem.id)
        assert versions[0].content == "Lives in Mumbai."
        assert ts(versions[0].valid_to) == T1

    @pytest.mark.asyncio
    async def test_invalidate_by_id(self, unit_session):
        user_id = await _user(unit_session)
        svc = MemoryService(unit_session)
        mem = await _assert_city(svc, user_id, "Lives in Mumbai.", T0)
        await svc.invalidate(mem.id, valid_to=T1)
        assert ts(mem.valid_to) == T1
        assert mem.status == "stale"


@pytest.mark.unit
class TestAsOfProjection:
    async def _three_generations(self, session):
        user_id = await _user(session)
        svc = MemoryService(session)
        await _assert_city(svc, user_id, "Lives in Mumbai.", T0)
        await _assert_city(svc, user_id, "Lives in Pune.", T1)
        await _assert_city(svc, user_id, "Lives in Berlin.", T2)
        await session.flush()
        return user_id, svc

    @pytest.mark.asyncio
    async def test_three_timestamps_give_three_answers(self, unit_session):
        user_id, svc = await self._three_generations(unit_session)
        mem = (await svc.list_memories(user_id=user_id))[0]
        temporal = TemporalService(unit_session)

        for at, expected in [
            (T0 + timedelta(days=1), "Lives in Mumbai."),
            (T1 + timedelta(days=1), "Lives in Pune."),
            (T2 + timedelta(days=1), "Lives in Berlin."),
        ]:
            views = await temporal.project_as_of([mem], at)
            assert len(views) == 1, f"expected a generation valid at {at}"
            assert views[0].content == expected

    @pytest.mark.asyncio
    async def test_before_first_generation_yields_nothing(self, unit_session):
        user_id, svc = await self._three_generations(unit_session)
        mem = (await svc.list_memories(user_id=user_id))[0]
        views = await TemporalService(unit_session).project_as_of([mem], T0 - timedelta(days=1))
        assert views == []

    @pytest.mark.asyncio
    async def test_search_as_of_returns_historical_content(self, unit_session):
        user_id, _ = await self._three_generations(unit_session)
        resp = await RetrievalService(unit_session).search(
            MemorySearchRequest(user_id=user_id, as_of=T1 + timedelta(days=1), top_k=5)
        )
        assert [r.memory.content for r in resp.results] == ["Lives in Pune."]

    @pytest.mark.asyncio
    async def test_search_without_as_of_returns_current(self, unit_session):
        user_id, _ = await self._three_generations(unit_session)
        resp = await RetrievalService(unit_session).search(
            MemorySearchRequest(user_id=user_id, top_k=5)
        )
        assert [r.memory.content for r in resp.results] == ["Lives in Berlin."]


@pytest.mark.unit
class TestTimeline:
    @pytest.mark.asyncio
    async def test_timeline_orders_generations_with_diffs(self, unit_session):
        user_id = await _user(unit_session)
        svc = MemoryService(unit_session)
        mem = await _assert_city(svc, user_id, "Lives in Mumbai.", T0)
        await _assert_city(svc, user_id, "Lives in Pune.", T1)
        await unit_session.flush()

        tl = await TemporalService(unit_session).timeline(mem.id)
        assert tl["generation_count"] == 2
        gens = tl["generations"]
        # Oldest first; only the last is current.
        assert gens[0]["content"] == "Lives in Mumbai."
        assert gens[0]["is_current"] is False
        assert gens[-1]["content"] == "Lives in Pune."
        assert gens[-1]["is_current"] is True
        # Per-hop diff describes the change.
        assert gens[0]["diff"]["kind"] == "created"
        assert gens[-1]["diff"]["kind"] == "revised"
        assert "Pune." in gens[-1]["diff"]["added"]
        assert "Mumbai." in gens[-1]["diff"]["removed"]
