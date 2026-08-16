"""Integration: team-aware retrieval visibility on real PostgreSQL."""

from __future__ import annotations

import uuid

import pytest

from app.models.user import User
from app.schemas.memory import MemorySearchRequest, MemoryUpsert
from app.services.access_service import AccessService
from app.services.memory_service import MemoryService
from app.services.retrieval_service import RetrievalService
from app.services.team_service import TeamService

pytestmark = pytest.mark.integration


async def _user(session, name) -> uuid.UUID:
    uid = uuid.uuid4()
    session.add(User(id=uid, name=name))
    await session.flush()
    return uid


@pytest.mark.asyncio
async def test_team_and_restricted_visibility(integration_session):
    session = integration_session
    owner = await _user(session, "owner")
    member = await _user(session, "member")
    outsider = await _user(session, "outsider")

    teams = TeamService(session)
    team = await teams.create_team(name="T", owner_user_id=owner)
    await teams.add_member(team_id=team.id, actor_user_id=owner, user_id=member)
    await teams.add_member(team_id=team.id, actor_user_id=owner, user_id=outsider)

    svc = MemoryService(session)
    team_mem, _ = await svc.upsert(
        MemoryUpsert(
            user_id=owner, memory_key="shared:team", memory_type="semantic", content="team fact"
        )
    )
    restricted_mem, _ = await svc.upsert(
        MemoryUpsert(
            user_id=owner, memory_key="shared:r", memory_type="semantic", content="secret fact"
        )
    )
    await session.flush()

    access = AccessService(session)
    await access.share_memory(
        memory_id=team_mem.id, actor_user_id=owner, visibility="team", team_id=team.id
    )
    await access.share_memory(
        memory_id=restricted_mem.id, actor_user_id=owner, visibility="restricted", team_id=team.id
    )
    await access.grant(
        memory_id=restricted_mem.id,
        actor_user_id=owner,
        principal_type="user",
        principal_id=str(member),
    )
    await session.flush()

    async def ids(viewer):
        resp = await RetrievalService(session).search(
            MemorySearchRequest(user_id=viewer, include_shared=True, top_k=20)
        )
        return {r.memory.id for r in resp.results}

    member_ids = await ids(member)
    outsider_ids = await ids(outsider)

    # Team memory: both team members see it.
    assert team_mem.id in member_ids
    assert team_mem.id in outsider_ids
    # Restricted memory: only the granted member sees it.
    assert restricted_mem.id in member_ids
    assert restricted_mem.id not in outsider_ids
