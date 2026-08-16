"""Team endpoints — create teams, manage membership."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import enforce_tenant, get_current_api_key
from app.db.session import get_session
from app.models.api_key import APIKey
from app.schemas.team import (
    MemberAddRequest,
    MemberRemoveRequest,
    MemberResponse,
    TeamCreate,
    TeamResponse,
)
from app.services.team_service import TeamService

router = APIRouter()


@router.post("", response_model=TeamResponse, status_code=201)
async def create_team(
    data: TeamCreate,
    session: AsyncSession = Depends(get_session),
    api_key: APIKey | None = Depends(get_current_api_key),
) -> TeamResponse:
    enforce_tenant(api_key, data.owner_user_id)
    team = await TeamService(session).create_team(name=data.name, owner_user_id=data.owner_user_id)
    return TeamResponse.model_validate(team)


@router.get("/{team_id}/members", response_model=list[MemberResponse])
async def list_members(
    team_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[MemberResponse]:
    members = await TeamService(session).list_members(team_id)
    return [MemberResponse.model_validate(m) for m in members]


@router.post("/{team_id}/members", response_model=MemberResponse, status_code=201)
async def add_member(
    team_id: uuid.UUID,
    data: MemberAddRequest,
    session: AsyncSession = Depends(get_session),
    api_key: APIKey | None = Depends(get_current_api_key),
) -> MemberResponse:
    """Add a member to a team. Only a team admin may do this."""
    enforce_tenant(api_key, data.actor_user_id)
    membership = await TeamService(session).add_member(
        team_id=team_id,
        actor_user_id=data.actor_user_id,
        user_id=data.user_id,
        role=data.role,
    )
    return MemberResponse.model_validate(membership)


@router.delete("/{team_id}/members/{user_id}", status_code=200)
async def remove_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    data: MemberRemoveRequest,
    session: AsyncSession = Depends(get_session),
    api_key: APIKey | None = Depends(get_current_api_key),
) -> dict:
    enforce_tenant(api_key, data.actor_user_id)
    removed = await TeamService(session).remove_member(
        team_id=team_id, actor_user_id=data.actor_user_id, user_id=user_id
    )
    return {"removed": removed}
