"""Unit tests for memory consolidation service."""

from __future__ import annotations

import uuid

import pytest

from app.models.user import User
from app.schemas.memory import MemoryUpsert
from app.services.consolidation_service import ConsolidationService
from app.services.memory_service import MemoryService


@pytest.mark.unit
class TestConsolidationService:
    async def _setup_user(self, session) -> uuid.UUID:
        user_id = uuid.uuid4()
        user = User(id=user_id, name="test-consolidation-user")
        session.add(user)
        await session.flush()
        return user_id

    @pytest.mark.asyncio
    async def test_find_exact_duplicates_empty(self, unit_session):
        """No memories → no duplicates."""
        user_id = await self._setup_user(unit_session)
        svc = ConsolidationService(unit_session)
        groups = await svc.find_exact_duplicates(user_id)
        assert groups == []

    @pytest.mark.asyncio
    async def test_find_exact_duplicates_with_dupes(self, unit_session):
        """Memories with identical content_hash should be grouped."""
        user_id = await self._setup_user(unit_session)
        mem_svc = MemoryService(unit_session)

        # Create two memories with different keys but same content
        for key in ("fact_a", "fact_b"):
            await mem_svc.upsert(
                MemoryUpsert(
                    user_id=user_id,
                    memory_key=key,
                    memory_type="semantic",
                    content="Identical content for dedup test.",
                )
            )
        await unit_session.flush()

        svc = ConsolidationService(unit_session)
        groups = await svc.find_exact_duplicates(user_id)
        assert len(groups) >= 1
        # Each group is a list of Memory objects with same content_hash
        for group in groups:
            assert len(group) >= 2

    @pytest.mark.asyncio
    async def test_merge_memories(self, unit_session):
        """Merging should archive the secondary and keep the primary."""
        user_id = await self._setup_user(unit_session)
        mem_svc = MemoryService(unit_session)

        m1, _ = await mem_svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="merge_target",
                memory_type="semantic",
                content="Primary content.",
                importance_score=0.5,
            )
        )
        m2, _ = await mem_svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="merge_secondary",
                memory_type="semantic",
                content="Secondary content.",
                importance_score=0.9,
            )
        )
        await unit_session.flush()

        svc = ConsolidationService(unit_session)
        primary = await svc.merge_memories(m1.id, m2.id)

        assert primary.id == m1.id
        # Should inherit the higher importance
        assert primary.importance_score >= 0.9

        # Secondary should be archived
        secondary = await mem_svc.get_memory(m2.id)
        assert secondary.status == "archived"
