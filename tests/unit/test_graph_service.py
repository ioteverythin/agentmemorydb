"""Unit tests for graph traversal service."""

from __future__ import annotations

import uuid

import pytest

from app.models.user import User
from app.schemas.memory import MemoryUpsert
from app.services.graph_service import GraphTraversalService
from app.services.memory_service import MemoryService


@pytest.mark.unit
class TestGraphTraversal:
    async def _setup_user(self, session) -> uuid.UUID:
        user_id = uuid.uuid4()
        user = User(id=user_id, name="test-graph-user")
        session.add(user)
        await session.flush()
        return user_id

    async def _create_memory(self, session, user_id, key, content):
        svc = MemoryService(session)
        mem, _ = await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key=key,
                memory_type="semantic",
                content=content,
            )
        )
        await session.flush()
        return mem

    @pytest.mark.asyncio
    async def test_expand_single_node(self, unit_session):
        """Expanding a node with no links should return just the seed."""
        user_id = await self._setup_user(unit_session)
        mem = await self._create_memory(
            unit_session, user_id, "lonely", "No connections"
        )
        svc = GraphTraversalService(unit_session)
        nodes = await svc.expand(mem.id, max_hops=2)
        assert len(nodes) == 1
        assert nodes[0]["memory_id"] == mem.id
        assert nodes[0]["depth"] == 0

    @pytest.mark.asyncio
    async def test_expand_follows_links(self, unit_session):
        """Expand should follow memory links up to max_hops."""
        user_id = await self._setup_user(unit_session)
        mem_svc = MemoryService(unit_session)

        m1 = await self._create_memory(unit_session, user_id, "n1", "Node 1")
        m2 = await self._create_memory(unit_session, user_id, "n2", "Node 2")
        m3 = await self._create_memory(unit_session, user_id, "n3", "Node 3")

        # m1 -> m2 -> m3
        await mem_svc.create_link(m1.id, m2.id, "supports")
        await mem_svc.create_link(m2.id, m3.id, "supports")
        await unit_session.flush()

        svc = GraphTraversalService(unit_session)

        # 1-hop: should get m1 + m2
        nodes_1 = await svc.expand(m1.id, max_hops=1)
        ids_1 = {n["memory_id"] for n in nodes_1}
        assert m1.id in ids_1
        assert m2.id in ids_1

        # 2-hop: should get all three
        nodes_2 = await svc.expand(m1.id, max_hops=2)
        ids_2 = {n["memory_id"] for n in nodes_2}
        assert m3.id in ids_2

    @pytest.mark.asyncio
    async def test_shortest_path_direct(self, unit_session):
        """Shortest path between directly linked nodes should be length 2."""
        user_id = await self._setup_user(unit_session)
        mem_svc = MemoryService(unit_session)

        m1 = await self._create_memory(unit_session, user_id, "a", "A")
        m2 = await self._create_memory(unit_session, user_id, "b", "B")
        await mem_svc.create_link(m1.id, m2.id, "related")
        await unit_session.flush()

        svc = GraphTraversalService(unit_session)
        path = await svc.find_shortest_path(m1.id, m2.id)
        assert path is not None
        assert len(path) == 2

    @pytest.mark.asyncio
    async def test_shortest_path_not_connected(self, unit_session):
        """No path between unlinked nodes should return None."""
        user_id = await self._setup_user(unit_session)
        m1 = await self._create_memory(unit_session, user_id, "x", "X")
        m2 = await self._create_memory(unit_session, user_id, "y", "Y")

        svc = GraphTraversalService(unit_session)
        path = await svc.find_shortest_path(m1.id, m2.id)
        assert path is None
