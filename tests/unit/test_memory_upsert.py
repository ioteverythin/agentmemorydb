"""Unit tests for memory upsert logic."""

from __future__ import annotations

import uuid

import pytest

from app.models.user import User
from app.schemas.memory import MemoryUpsert
from app.services.memory_service import MemoryService


@pytest.mark.unit
class TestMemoryUpsert:
    """Test the core upsert behaviour using in-memory SQLite."""

    async def _setup_user(self, session) -> uuid.UUID:
        """Insert a minimal user row and return its ID."""
        user_id = uuid.uuid4()
        user = User(id=user_id, name="test-user")
        session.add(user)
        await session.flush()
        return user_id

    @pytest.mark.asyncio
    async def test_create_new_memory(self, unit_session):
        """Upsert with no prior record should create a new memory."""
        user_id = await self._setup_user(unit_session)
        svc = MemoryService(unit_session)

        data = MemoryUpsert(
            user_id=user_id,
            memory_key="user_preference_color",
            memory_type="semantic",
            content="The user prefers blue.",
            confidence=0.9,
        )
        memory, is_new = await svc.upsert(data)

        assert is_new is True
        assert memory.content == "The user prefers blue."
        assert memory.version == 1
        assert memory.status == "active"
        assert memory.confidence == 0.9

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, unit_session):
        """Upsert with same key should update the canonical memory."""
        user_id = await self._setup_user(unit_session)
        svc = MemoryService(unit_session)

        data1 = MemoryUpsert(
            user_id=user_id,
            memory_key="user_preference_color",
            memory_type="semantic",
            content="The user prefers blue.",
        )
        mem1, is_new1 = await svc.upsert(data1)
        assert is_new1 is True

        data2 = MemoryUpsert(
            user_id=user_id,
            memory_key="user_preference_color",
            memory_type="semantic",
            content="The user now prefers green.",
            confidence=0.95,
        )
        mem2, is_new2 = await svc.upsert(data2)

        assert is_new2 is False
        assert mem2.id == mem1.id
        assert mem2.content == "The user now prefers green."
        assert mem2.version == 2
        assert mem2.confidence == 0.95

    @pytest.mark.asyncio
    async def test_upsert_identical_content_skips(self, unit_session):
        """Upserting identical content should not bump version."""
        user_id = await self._setup_user(unit_session)
        svc = MemoryService(unit_session)

        data = MemoryUpsert(
            user_id=user_id,
            memory_key="fact_1",
            memory_type="semantic",
            content="Water boils at 100°C at sea level.",
        )
        mem1, _ = await svc.upsert(data)
        mem2, is_new = await svc.upsert(data)

        assert is_new is False
        assert mem2.version == 1  # Not bumped

    @pytest.mark.asyncio
    async def test_upsert_creates_version_snapshot(self, unit_session):
        """Updating content should create a version snapshot."""
        user_id = await self._setup_user(unit_session)
        svc = MemoryService(unit_session)

        data1 = MemoryUpsert(
            user_id=user_id,
            memory_key="evolving_fact",
            memory_type="episodic",
            content="Version 1 content.",
        )
        await svc.upsert(data1)

        data2 = MemoryUpsert(
            user_id=user_id,
            memory_key="evolving_fact",
            memory_type="episodic",
            content="Version 2 content.",
        )
        mem, _ = await svc.upsert(data2)

        versions = await svc.get_versions(mem.id)
        assert len(versions) == 1
        assert versions[0].version == 1
        assert versions[0].content == "Version 1 content."

    @pytest.mark.asyncio
    async def test_upsert_different_keys_are_separate(self, unit_session):
        """Different memory_keys should create separate memories."""
        user_id = await self._setup_user(unit_session)
        svc = MemoryService(unit_session)

        mem_a, _ = await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="key_a",
                memory_type="semantic",
                content="Content A",
            )
        )
        mem_b, _ = await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="key_b",
                memory_type="semantic",
                content="Content B",
            )
        )

        assert mem_a.id != mem_b.id
