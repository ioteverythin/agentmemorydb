"""Integration test: event → observation → memory pipeline.

These tests use in-memory SQLite (no pgvector), so vector search
is not tested here.  They validate the data-flow pipeline logic.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.agent_run import AgentRun
from app.models.user import User
from app.schemas.event import EventCreate
from app.schemas.memory import MemoryUpsert
from app.services.event_service import EventService
from app.services.memory_service import MemoryService
from app.services.observation_service import ObservationService


@pytest.mark.integration
class TestEventToMemoryFlow:
    """End-to-end pipeline: event → observation → memory."""

    async def _setup(self, session):
        user_id = uuid.uuid4()
        user = User(id=user_id, name="pipeline-test-user")
        session.add(user)
        await session.flush()

        run_id = uuid.uuid4()
        run = AgentRun(id=run_id, user_id=user_id, status="running")
        session.add(run)
        await session.flush()

        return user_id, run_id

    @pytest.mark.asyncio
    async def test_full_pipeline(self, unit_session):
        """Create event → extract observation → upsert memory."""
        user_id, run_id = await self._setup(unit_session)

        # 1. Create event
        event_svc = EventService(unit_session)
        event = await event_svc.create_event(
            EventCreate(
                run_id=run_id,
                user_id=user_id,
                event_type="user_input",
                content="My favorite programming language is Python.",
            )
        )
        assert event.id is not None

        # 2. Extract observations
        obs_svc = ObservationService(unit_session)
        observations = await obs_svc.extract_from_event(event.id)
        assert len(observations) >= 1
        obs = observations[0]
        assert obs.content == "My favorite programming language is Python."
        assert obs.source_type == "user_input"
        assert obs.confidence == 0.8

        # 3. Upsert memory from observation
        mem_svc = MemoryService(unit_session)
        memory, is_new = await mem_svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="fav_language",
                memory_type="semantic",
                content=obs.content,
                source_type=obs.source_type,
                source_event_id=event.id,
                source_observation_id=obs.id,
                source_run_id=run_id,
                confidence=obs.confidence,
            )
        )
        assert is_new is True
        assert memory.memory_key == "fav_language"
        assert memory.status == "active"

    @pytest.mark.asyncio
    async def test_non_extractable_event_yields_no_observations(self, unit_session):
        """Events of non-extractable types should produce no observations."""
        user_id, run_id = await self._setup(unit_session)

        event_svc = EventService(unit_session)
        event = await event_svc.create_event(
            EventCreate(
                run_id=run_id,
                user_id=user_id,
                event_type="planner_step",
                content="Planning next action...",
            )
        )

        obs_svc = ObservationService(unit_session)
        observations = await obs_svc.extract_from_event(event.id)
        assert len(observations) == 0
