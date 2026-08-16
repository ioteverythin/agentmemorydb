"""Tests for Observation → Memory promotion (completing the pipeline)."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.models.user import User
from app.schemas.observation import (
    ObservationCreate,
    ObservationPromoteRequest,
)
from app.services.memory_service import MemoryService
from app.services.observation_service import ObservationService


async def _user(session) -> uuid.UUID:
    uid = uuid.uuid4()
    session.add(User(id=uid, name="promo-user"))
    await session.flush()
    return uid


async def _observation(session, user_id, content="the user prefers dark mode"):
    svc = ObservationService(session)
    return await svc.create_observation(
        ObservationCreate(
            event_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            user_id=user_id,
            content=content,
            observation_type="user_input",
            source_type="user_input",
            confidence=0.8,
        )
    )


@pytest.mark.unit
class TestObservationPromotion:
    @pytest.mark.asyncio
    async def test_promote_creates_memory_with_provenance(self, unit_session):
        user_id = await _user(unit_session)
        obs = await _observation(unit_session, user_id)

        svc = ObservationService(unit_session)
        promoted, memory, created = await svc.promote(
            obs.id,
            ObservationPromoteRequest(memory_key="pref:theme", importance_score=0.7),
        )

        assert created is True
        assert memory.content == obs.content
        assert memory.memory_key == "pref:theme"
        assert memory.importance_score == 0.7
        # Provenance is carried onto the memory.
        assert memory.source_observation_id == obs.id
        assert memory.source_event_id == obs.event_id
        assert memory.source_run_id == obs.run_id
        # Observation is accepted and linked.
        assert promoted.status == "accepted"
        assert promoted.memory_id == memory.id

    @pytest.mark.asyncio
    async def test_human_verified_sets_source_type(self, unit_session):
        user_id = await _user(unit_session)
        obs = await _observation(unit_session, user_id)
        svc = ObservationService(unit_session)
        _, memory, _ = await svc.promote(
            obs.id,
            ObservationPromoteRequest(memory_key="fact:1", human_verified=True),
        )
        assert memory.source_type == "human_verified"

    @pytest.mark.asyncio
    async def test_second_promotion_same_key_updates(self, unit_session):
        user_id = await _user(unit_session)
        svc = ObservationService(unit_session)

        obs1 = await _observation(unit_session, user_id, "first")
        _, mem1, created1 = await svc.promote(
            obs1.id, ObservationPromoteRequest(memory_key="k:same")
        )
        assert created1 is True

        obs2 = await _observation(unit_session, user_id, "second")
        _, mem2, created2 = await svc.promote(
            obs2.id, ObservationPromoteRequest(memory_key="k:same")
        )
        assert created2 is False
        assert mem2.id == mem1.id
        assert mem2.content == "second"
        assert mem2.version == 2

    @pytest.mark.asyncio
    async def test_reject_blocks_promotion(self, unit_session):
        user_id = await _user(unit_session)
        obs = await _observation(unit_session, user_id)
        svc = ObservationService(unit_session)

        rejected = await svc.reject(obs.id, reason="not useful")
        assert rejected.status == "rejected"
        assert rejected.metadata_["rejection_reason"] == "not useful"

        with pytest.raises(HTTPException) as exc:
            await svc.promote(obs.id, ObservationPromoteRequest(memory_key="nope"))
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_promoted_memory_is_retrievable(self, unit_session):
        """After promotion the memory is a normal, listable memory."""
        user_id = await _user(unit_session)
        obs = await _observation(unit_session, user_id, "retrieve me")
        svc = ObservationService(unit_session)
        _, memory, _ = await svc.promote(obs.id, ObservationPromoteRequest(memory_key="r:1"))

        mems = await MemoryService(unit_session).list_memories(user_id=user_id)
        assert memory.id in {m.id for m in mems}
