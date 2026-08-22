"""Integration: bitemporal as-of queries against real PostgreSQL.

The point-in-time predicate uses an EXISTS subquery over ``memory_versions``,
so it must be exercised on the real engine (the SQLite harness has no
TIMESTAMPTZ and a different comparison model).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.user import User
from app.schemas.memory import MemorySearchRequest, MemoryUpsert
from app.services.memory_service import MemoryService
from app.services.retrieval_service import RetrievalService
from app.services.temporal_service import TemporalService

pytestmark = pytest.mark.integration

T0 = datetime(2026, 1, 1, tzinfo=UTC)
T1 = datetime(2026, 3, 1, tzinfo=UTC)
T2 = datetime(2026, 6, 1, tzinfo=UTC)


@pytest.mark.asyncio
async def test_preference_changes_twice_and_as_of_gives_three_answers(integration_session):
    session = integration_session
    user_id = uuid.uuid4()
    session.add(User(id=user_id, name="temporal-int"))
    await session.flush()

    svc = MemoryService(session)
    for content, valid_from in [
        ("The user lives in Mumbai.", T0),
        ("The user lives in Pune.", T1),
        ("The user lives in Berlin.", T2),
    ]:
        await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="fact:city",
                memory_type="semantic",
                content=content,
                valid_from=valid_from,
            )
        )
    await session.flush()

    retr = RetrievalService(session)

    async def city_at(as_of):
        resp = await retr.search(
            MemorySearchRequest(
                user_id=user_id, query_text="where does the user live", as_of=as_of, top_k=5
            )
        )
        return [r.memory.content for r in resp.results]

    # Three timestamps → three different answers, all in plain SQL.
    assert await city_at(T0 + timedelta(days=1)) == ["The user lives in Mumbai."]
    assert await city_at(T1 + timedelta(days=1)) == ["The user lives in Pune."]
    assert await city_at(T2 + timedelta(days=1)) == ["The user lives in Berlin."]

    # Before the fact existed at all → nothing.
    assert await city_at(T0 - timedelta(days=1)) == []

    # No as_of → the current generation.
    now_resp = await retr.search(
        MemorySearchRequest(user_id=user_id, query_text="where does the user live", top_k=5)
    )
    assert [r.memory.content for r in now_resp.results] == ["The user lives in Berlin."]


@pytest.mark.asyncio
async def test_timeline_chain_on_postgres(integration_session):
    session = integration_session
    user_id = uuid.uuid4()
    session.add(User(id=user_id, name="timeline-int"))
    await session.flush()

    svc = MemoryService(session)
    mem, _ = await svc.upsert(
        MemoryUpsert(
            user_id=user_id,
            memory_key="pref:editor",
            memory_type="semantic",
            content="Uses Vim.",
            valid_from=T0,
        )
    )
    await svc.upsert(
        MemoryUpsert(
            user_id=user_id,
            memory_key="pref:editor",
            memory_type="semantic",
            content="Uses VS Code.",
            valid_from=T1,
        )
    )
    await session.flush()

    tl = await TemporalService(session).timeline(mem.id)
    assert tl["generation_count"] == 2
    assert [g["content"] for g in tl["generations"]] == ["Uses Vim.", "Uses VS Code."]
    assert tl["generations"][-1]["is_current"] is True
    assert tl["generations"][0]["valid_to"] is not None
