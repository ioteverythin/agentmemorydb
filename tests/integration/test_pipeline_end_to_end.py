"""End-to-end Event → Observation → Memory pipeline against real PostgreSQL.

Exercises the full advertised flow with FK constraints enforced: create a run,
append an event, extract an observation, promote it to a memory, and confirm
the memory is retrievable and carries provenance.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.agent_run import AgentRun
from app.models.user import User
from app.schemas.event import EventCreate
from app.schemas.memory import MemorySearchRequest
from app.schemas.observation import ObservationPromoteRequest
from app.services.event_service import EventService
from app.services.observation_service import ObservationService
from app.services.retrieval_service import RetrievalService

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_event_to_observation_to_memory(integration_session):
    session = integration_session

    # Real user + run so FK constraints are satisfied.
    user_id = uuid.uuid4()
    session.add(User(id=user_id, name="pipeline-user"))
    await session.flush()  # user must exist before the run's FK
    run = AgentRun(user_id=user_id, agent_name="agent")
    session.add(run)
    await session.flush()

    # 1. Record an event.
    event = await EventService(session).create_event(
        EventCreate(
            run_id=run.id,
            user_id=user_id,
            event_type="user_input",
            content="Remember that the primary datastore is PostgreSQL.",
        )
    )

    # 2. Extract observation(s) from it.
    obs_svc = ObservationService(session)
    observations = await obs_svc.extract_from_event(event.id)
    assert observations, "rule-based extraction should yield an observation"
    obs = observations[0]
    assert obs.status == "pending"

    # 3. Promote the observation into a canonical memory.
    promoted, memory, created = await obs_svc.promote(
        obs.id,
        ObservationPromoteRequest(memory_key="fact:datastore", importance_score=0.9),
    )
    assert created is True
    assert promoted.status == "accepted"
    assert promoted.memory_id == memory.id
    assert memory.source_event_id == event.id
    assert memory.source_observation_id == obs.id
    await session.flush()

    # 4. The promoted memory is retrievable via search.
    resp = await RetrievalService(session).search(
        MemorySearchRequest(user_id=user_id, query_text="datastore PostgreSQL", top_k=5)
    )
    assert memory.id in {r.memory.id for r in resp.results}
