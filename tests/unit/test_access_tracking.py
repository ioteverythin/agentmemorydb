"""Unit tests for access tracking service."""

from __future__ import annotations

import uuid

import pytest

from app.models.user import User
from app.schemas.memory import MemoryUpsert
from app.services.access_tracking_service import AccessTrackingService
from app.services.memory_service import MemoryService


@pytest.mark.unit
class TestAccessTracking:
    async def _setup_user(self, session) -> uuid.UUID:
        user_id = uuid.uuid4()
        user = User(id=user_id, name="test-access-user")
        session.add(user)
        await session.flush()
        return user_id

    async def _create_memory(self, session, user_id, key="test_mem"):
        svc = MemoryService(session)
        mem, _ = await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key=key,
                memory_type="semantic",
                content=f"Content for {key}",
            )
        )
        await session.flush()
        return mem

    @pytest.mark.asyncio
    async def test_log_access(self, unit_session):
        """Logging a single access should create an access record."""
        user_id = await self._setup_user(unit_session)
        mem = await self._create_memory(unit_session, user_id)

        svc = AccessTrackingService(unit_session)
        log = await svc.log_access(
            memory_id=mem.id,
            user_id=user_id,
            access_type="retrieval",
        )
        assert log.memory_id == mem.id
        assert log.access_type == "retrieval"

    @pytest.mark.asyncio
    async def test_log_batch_access(self, unit_session):
        """Batch logging should create one record per memory."""
        user_id = await self._setup_user(unit_session)
        m1 = await self._create_memory(unit_session, user_id, "batch_a")
        m2 = await self._create_memory(unit_session, user_id, "batch_b")

        svc = AccessTrackingService(unit_session)
        count = await svc.log_batch_access(
            memory_ids=[m1.id, m2.id],
            user_id=user_id,
            access_type="retrieval",
        )
        assert count == 2

    @pytest.mark.asyncio
    async def test_get_access_count(self, unit_session):
        """Count should reflect logged accesses."""
        user_id = await self._setup_user(unit_session)
        mem = await self._create_memory(unit_session, user_id, "counted")

        svc = AccessTrackingService(unit_session)
        # Log 3 accesses
        for _ in range(3):
            await svc.log_access(mem.id, user_id, access_type="retrieval")
        await unit_session.flush()

        count = await svc.get_access_count(mem.id)
        assert count == 3
