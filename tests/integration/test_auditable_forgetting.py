"""Integration: erasure against real PostgreSQL FK cascades.

Hard erasure only works if every child row referencing the memory goes with it —
versions, links, ACL grants, access logs, retrieval-log items. Those cascades are
database behaviour, so they cannot be verified on the SQLite unit harness.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update

from app.models.forgetting_log import ForgettingLog
from app.models.memory import Memory
from app.models.memory_access_log import MemoryAccessLog
from app.models.memory_version import MemoryVersion
from app.models.user import User
from app.schemas.memory import MemoryUpsert
from app.services.forgetting_service import ForgettingService
from app.services.memory_service import MemoryService

pytestmark = pytest.mark.integration


async def _seeded_memory(session) -> Memory:
    user_id = uuid.uuid4()
    session.add(User(id=user_id, name="erase-int"))
    await session.flush()

    svc = MemoryService(session)
    memory, _ = await svc.upsert(
        MemoryUpsert(
            user_id=user_id,
            memory_key="pref:city",
            memory_type="semantic",
            content="The user lives in Mumbai.",
        ),
        emit=False,
    )
    # A second write creates a version row to cascade.
    memory, _ = await svc.upsert(
        MemoryUpsert(
            user_id=user_id,
            memory_key="pref:city",
            memory_type="semantic",
            content="The user lives in Pune.",
        ),
        emit=False,
    )
    session.add(MemoryAccessLog(memory_id=memory.id, user_id=user_id))
    await session.flush()
    return memory


@pytest.mark.asyncio
async def test_erase_cascades_children_and_leaves_a_tombstone(integration_session):
    session = integration_session
    memory = await _seeded_memory(session)
    memory_id, user_id = memory.id, memory.user_id
    content_hash = memory.content_hash

    assert (
        await session.scalar(
            select(func.count())
            .select_from(MemoryVersion)
            .where(MemoryVersion.memory_id == memory_id)
        )
        > 0
    )

    report = await ForgettingService(session).erase_memory(memory_id, reason="integration erasure")
    assert report["erased"] == 1
    await session.flush()

    assert await session.get(Memory, memory_id) is None
    assert (
        await session.scalar(
            select(func.count())
            .select_from(MemoryVersion)
            .where(MemoryVersion.memory_id == memory_id)
        )
        == 0
    )
    # Access logs cascade at the database level.
    assert (
        await session.scalar(
            select(func.count())
            .select_from(MemoryAccessLog)
            .where(MemoryAccessLog.memory_id == memory_id)
        )
        == 0
    )

    # The tombstone has no FK to memories, so it survives the delete.
    rows = (
        (await session.execute(select(ForgettingLog).where(ForgettingLog.memory_id == memory_id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].content_hash == content_hash
    assert rows[0].user_id == user_id
    assert rows[0].reason == "integration erasure"


@pytest.mark.asyncio
async def test_pinned_memory_is_excluded_from_decay_on_postgres(integration_session):
    """``pinned`` is a real NOT NULL column, and the decay scan honours it in SQL."""
    session = integration_session
    memory = await _seeded_memory(session)
    assert memory.pinned is False

    # Age it well past the half-life so decay would definitely apply…
    old = datetime.now(UTC) - timedelta(days=365)
    await session.execute(
        update(Memory).where(Memory.id == memory.id).values(updated_at=old, importance_score=0.8)
    )
    # …then pin it, which must take it out of the candidate set entirely.
    await MemoryService(session).set_pinned(memory.id, pinned=True)
    await session.flush()

    report = await ForgettingService(session).decay_importance()
    assert report["decayed"] == 0

    refreshed = await session.get(Memory, memory.id)
    assert refreshed is not None
    assert refreshed.pinned is True
    assert refreshed.importance_score == 0.8
