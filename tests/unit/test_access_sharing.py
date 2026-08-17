"""Tests for memory sharing, ACL grants, and team-aware retrieval visibility."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.models.user import User
from app.schemas.memory import MemorySearchRequest, MemoryUpsert
from app.services.access_service import AccessService
from app.services.memory_service import MemoryService
from app.services.retrieval_service import RetrievalService
from app.services.team_service import TeamService


async def _user(session, name) -> uuid.UUID:
    uid = uuid.uuid4()
    session.add(User(id=uid, name=name))
    await session.flush()
    return uid


async def _memory(session, owner, key="m1", content="a shared fact"):
    mem, _ = await MemoryService(session).upsert(
        MemoryUpsert(user_id=owner, memory_key=key, memory_type="semantic", content=content)
    )
    await session.flush()
    return mem


async def _search_ids(session, viewer, *, include_shared=True, as_agent_id=None) -> set[uuid.UUID]:
    resp = await RetrievalService(session).search(
        MemorySearchRequest(
            user_id=viewer, include_shared=include_shared, as_agent_id=as_agent_id, top_k=20
        )
    )
    return {r.memory.id for r in resp.results}


@pytest.mark.unit
class TestTeamVisibility:
    @pytest.mark.asyncio
    async def test_team_member_sees_shared_memory(self, unit_session):
        owner = await _user(unit_session, "owner")
        member = await _user(unit_session, "member")
        outsider = await _user(unit_session, "outsider")

        team = await TeamService(unit_session).create_team(name="T", owner_user_id=owner)
        await TeamService(unit_session).add_member(
            team_id=team.id, actor_user_id=owner, user_id=member
        )
        mem = await _memory(unit_session, owner)
        await AccessService(unit_session).share_memory(
            memory_id=mem.id, actor_user_id=owner, visibility="team", team_id=team.id
        )
        await unit_session.flush()

        # Member sees it (shared); outsider does not; and without include_shared nobody else does.
        assert mem.id in await _search_ids(unit_session, member)
        assert mem.id not in await _search_ids(unit_session, outsider)
        assert mem.id not in await _search_ids(unit_session, member, include_shared=False)

    @pytest.mark.asyncio
    async def test_restricted_visible_only_to_granted_user(self, unit_session):
        owner = await _user(unit_session, "owner")
        member = await _user(unit_session, "member")
        other = await _user(unit_session, "other")
        team = await TeamService(unit_session).create_team(name="T", owner_user_id=owner)
        for u in (member, other):
            await TeamService(unit_session).add_member(
                team_id=team.id, actor_user_id=owner, user_id=u
            )
        mem = await _memory(unit_session, owner)
        access = AccessService(unit_session)
        await access.share_memory(
            memory_id=mem.id, actor_user_id=owner, visibility="restricted", team_id=team.id
        )
        await access.grant(
            memory_id=mem.id,
            actor_user_id=owner,
            principal_type="user",
            principal_id=str(member),
        )
        await unit_session.flush()

        assert mem.id in await _search_ids(unit_session, member)
        assert mem.id not in await _search_ids(unit_session, other)

    @pytest.mark.asyncio
    async def test_agent_bound_memory_only_for_that_agent(self, unit_session):
        owner = await _user(unit_session, "owner")
        member = await _user(unit_session, "member")
        team = await TeamService(unit_session).create_team(name="T", owner_user_id=owner)
        await TeamService(unit_session).add_member(
            team_id=team.id, actor_user_id=owner, user_id=member
        )
        mem = await _memory(unit_session, owner)
        await AccessService(unit_session).share_memory(
            memory_id=mem.id,
            actor_user_id=owner,
            visibility="agent",
            team_id=team.id,
            agent_id="scout",
        )
        await unit_session.flush()

        assert mem.id in await _search_ids(unit_session, member, as_agent_id="scout")
        assert mem.id not in await _search_ids(unit_session, member, as_agent_id="builder")
        assert mem.id not in await _search_ids(unit_session, member)  # no agent context


@pytest.mark.unit
class TestSharingEnforcement:
    @pytest.mark.asyncio
    async def test_only_owner_can_share(self, unit_session):
        owner = await _user(unit_session, "owner")
        other = await _user(unit_session, "other")
        team = await TeamService(unit_session).create_team(name="T", owner_user_id=owner)
        mem = await _memory(unit_session, owner)
        with pytest.raises(HTTPException) as exc:
            await AccessService(unit_session).share_memory(
                memory_id=mem.id, actor_user_id=other, visibility="team", team_id=team.id
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_share_into_team_you_are_not_in(self, unit_session):
        owner = await _user(unit_session, "owner")
        stranger = await _user(unit_session, "stranger")
        # A team owned by someone else that `owner` is not a member of.
        foreign = await TeamService(unit_session).create_team(name="F", owner_user_id=stranger)
        mem = await _memory(unit_session, owner)
        with pytest.raises(HTTPException) as exc:
            await AccessService(unit_session).share_memory(
                memory_id=mem.id, actor_user_id=owner, visibility="team", team_id=foreign.id
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_team_visibility_requires_team_id(self, unit_session):
        owner = await _user(unit_session, "owner")
        mem = await _memory(unit_session, owner)
        with pytest.raises(HTTPException) as exc:
            await AccessService(unit_session).share_memory(
                memory_id=mem.id, actor_user_id=owner, visibility="team"
            )
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_making_private_clears_sharing(self, unit_session):
        owner = await _user(unit_session, "owner")
        team = await TeamService(unit_session).create_team(name="T", owner_user_id=owner)
        mem = await _memory(unit_session, owner)
        access = AccessService(unit_session)
        await access.share_memory(
            memory_id=mem.id, actor_user_id=owner, visibility="team", team_id=team.id
        )
        await access.share_memory(memory_id=mem.id, actor_user_id=owner, visibility="private")
        assert mem.visibility == "private"
        assert mem.team_id is None
