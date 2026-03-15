"""Integration test: memory search with metadata filters.

Uses in-memory SQLite (no pgvector), so only metadata-path is tested.
For vector search, run against a real Postgres with pgvector.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.user import User
from app.schemas.memory import MemoryUpsert
from app.services.memory_service import MemoryService


@pytest.mark.integration
class TestMemorySearch:
    """Test metadata-based search, status/validity filtering."""

    async def _setup(self, session):
        user_id = uuid.uuid4()
        user = User(id=user_id, name="search-test-user")
        session.add(user)
        await session.flush()
        return user_id

    @pytest.mark.asyncio
    async def test_list_by_status(self, unit_session):
        """Listing memories should respect status filter."""
        user_id = await self._setup(unit_session)
        svc = MemoryService(unit_session)

        # Create two memories
        await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="active_mem",
                memory_type="semantic",
                content="I am active.",
            )
        )
        mem_archived, _ = await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="archived_mem",
                memory_type="semantic",
                content="I will be archived.",
            )
        )
        from app.schemas.memory import MemoryStatusUpdate

        await svc.update_status(mem_archived.id, MemoryStatusUpdate(status="archived"))

        # List only active
        active = await svc.list_memories(user_id=user_id, status="active")
        assert len(active) == 1
        assert active[0].memory_key == "active_mem"

        # List only archived
        archived = await svc.list_memories(user_id=user_id, status="archived")
        assert len(archived) == 1
        assert archived[0].memory_key == "archived_mem"

    @pytest.mark.asyncio
    async def test_list_by_memory_type(self, unit_session):
        """Listing memories should filter by memory_type."""
        user_id = await self._setup(unit_session)
        svc = MemoryService(unit_session)

        await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="sem1",
                memory_type="semantic",
                content="Semantic memory.",
            )
        )
        await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="epi1",
                memory_type="episodic",
                content="Episodic memory.",
            )
        )

        semantic = await svc.list_memories(user_id=user_id, memory_type="semantic")
        assert len(semantic) == 1
        assert semantic[0].memory_type == "semantic"

    @pytest.mark.asyncio
    async def test_list_by_scope(self, unit_session):
        """Listing memories should filter by scope."""
        user_id = await self._setup(unit_session)
        svc = MemoryService(unit_session)

        await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="user_mem",
                memory_type="semantic",
                scope="user",
                content="User-scoped.",
            )
        )
        await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="global_mem",
                memory_type="semantic",
                scope="global",
                content="Global-scoped.",
            )
        )

        user_mems = await svc.list_memories(user_id=user_id, scope="user")
        assert len(user_mems) == 1
        assert user_mems[0].scope == "user"
