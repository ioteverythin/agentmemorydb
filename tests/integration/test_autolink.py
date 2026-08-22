"""Integration: autolinking against real PostgreSQL.

Verifies the thing the unit harness cannot: that autolinked edges are real rows
graph traversal actually walks, with pgvector-typed embeddings driving the
similarity.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.memory import Memory
from app.models.memory_link import MemoryLink
from app.models.user import User
from app.services.autolink_service import LINK_TYPE, AutolinkService
from app.services.graph_service import GraphTraversalService
from app.utils.embedding_provider import get_embedding_provider

pytestmark = pytest.mark.integration


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "enable_autolink", True)


async def _seed(session, *, count: int = 3) -> tuple[uuid.UUID, list[Memory]]:
    user_id = uuid.uuid4()
    session.add(User(id=user_id, name="autolink-int"))
    await session.flush()

    probe = (await get_embedding_provider().embed(["probe"]))[0]
    vector = [0.0] * len(probe)
    vector[0] = 1.0

    memories = []
    for i in range(count):
        memory = Memory(
            id=uuid.uuid4(),
            user_id=user_id,
            memory_key=f"fact:pg-{i}",
            memory_type="semantic",
            layer="atom",
            content=f"Uses Postgres for service {i}.",
            content_hash=f"autolink-int-{i}",
            status="active",
            embedding=vector,
            confidence=0.7,
            importance_score=0.5,
            authority_level=1,
        )
        session.add(memory)
        memories.append(memory)
    await session.flush()
    return user_id, memories


@pytest.mark.asyncio
async def test_autolinked_edges_are_traversable(integration_session, enabled):
    session = integration_session
    _user_id, memories = await _seed(session)
    subject = memories[-1]

    created = await AutolinkService(session).autolink(subject)
    await session.flush()
    assert len(created) == 2

    nodes = await GraphTraversalService(session).expand(
        seed_memory_id=subject.id, max_hops=1, link_types=[LINK_TYPE]
    )
    reached = {str(n["memory_id"]) for n in nodes}
    assert {str(m.id) for m in memories[:-1]} <= reached


@pytest.mark.asyncio
async def test_backfill_then_rerun_is_idempotent(integration_session, enabled):
    session = integration_session
    user_id, _memories = await _seed(session, count=4)
    svc = AutolinkService(session)

    first = await svc.backfill(user_id)
    await session.flush()
    assert first["memories_scanned"] == 4
    assert first["links_created"] > 0

    second = await svc.backfill(user_id)
    assert second["links_created"] == 0

    edges = (
        (await session.execute(select(MemoryLink).where(MemoryLink.link_type == LINK_TYPE)))
        .scalars()
        .all()
    )
    assert len(edges) == first["links_created"]
    # No edge is stored in both directions.
    pairs = {frozenset((e.source_memory_id, e.target_memory_id)) for e in edges}
    assert len(pairs) == len(edges)
