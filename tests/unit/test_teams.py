"""Tests for team CRUD, membership roles, and enforcement."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.models.user import User
from app.services.team_service import TeamService


async def _user(session, name="u") -> uuid.UUID:
    uid = uuid.uuid4()
    session.add(User(id=uid, name=name))
    await session.flush()
    return uid


@pytest.mark.unit
class TestTeams:
    @pytest.mark.asyncio
    async def test_create_team_adds_owner_as_admin(self, unit_session):
        owner = await _user(unit_session, "owner")
        svc = TeamService(unit_session)
        team = await svc.create_team(name="Acme", owner_user_id=owner)

        assert team.owner_user_id == owner
        assert await svc.is_admin(team.id, owner) is True
        assert await svc.get_user_team_ids(owner) == [team.id]

    @pytest.mark.asyncio
    async def test_admin_can_add_member(self, unit_session):
        owner = await _user(unit_session, "owner")
        alice = await _user(unit_session, "alice")
        svc = TeamService(unit_session)
        team = await svc.create_team(name="Acme", owner_user_id=owner)

        m = await svc.add_member(team_id=team.id, actor_user_id=owner, user_id=alice)
        assert m.role == "member"
        assert await svc.is_member(team.id, alice) is True
        assert await svc.is_admin(team.id, alice) is False

    @pytest.mark.asyncio
    async def test_non_admin_cannot_add_member(self, unit_session):
        owner = await _user(unit_session, "owner")
        alice = await _user(unit_session, "alice")
        bob = await _user(unit_session, "bob")
        svc = TeamService(unit_session)
        team = await svc.create_team(name="Acme", owner_user_id=owner)
        await svc.add_member(team_id=team.id, actor_user_id=owner, user_id=alice)  # member

        with pytest.raises(HTTPException) as exc:
            await svc.add_member(team_id=team.id, actor_user_id=alice, user_id=bob)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_add_member_idempotent_updates_role(self, unit_session):
        owner = await _user(unit_session, "owner")
        alice = await _user(unit_session, "alice")
        svc = TeamService(unit_session)
        team = await svc.create_team(name="Acme", owner_user_id=owner)

        await svc.add_member(team_id=team.id, actor_user_id=owner, user_id=alice, role="member")
        await svc.add_member(team_id=team.id, actor_user_id=owner, user_id=alice, role="admin")
        assert await svc.is_admin(team.id, alice) is True
        assert len(await svc.list_members(team.id)) == 2  # owner + alice, no dup

    @pytest.mark.asyncio
    async def test_owner_cannot_be_removed(self, unit_session):
        owner = await _user(unit_session, "owner")
        svc = TeamService(unit_session)
        team = await svc.create_team(name="Acme", owner_user_id=owner)
        with pytest.raises(HTTPException) as exc:
            await svc.remove_member(team_id=team.id, actor_user_id=owner, user_id=owner)
        assert exc.value.status_code == 400
