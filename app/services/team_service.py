"""Team service — teams, memberships, and role checks."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.team import Team, TeamMembership


class TeamService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_team(self, *, name: str, owner_user_id: uuid.UUID) -> Team:
        """Create a team and add the owner as an admin member."""
        team = Team(name=name, owner_user_id=owner_user_id)
        self._session.add(team)
        await self._session.flush()
        self._session.add(TeamMembership(team_id=team.id, user_id=owner_user_id, role="admin"))
        await self._session.flush()
        return team

    async def get_team(self, team_id: uuid.UUID) -> Team:
        team = await self._session.get(Team, team_id)
        if team is None:
            raise NotFoundError("Team", team_id)
        return team

    async def add_member(
        self,
        *,
        team_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str = "member",
    ) -> TeamMembership:
        """Add a member. Only a team admin may add members."""
        await self.get_team(team_id)
        await self._require_admin(team_id, actor_user_id)

        existing = await self._membership(team_id, user_id)
        if existing is not None:
            existing.role = role  # idempotent: update role
            return existing

        membership = TeamMembership(team_id=team_id, user_id=user_id, role=role)
        self._session.add(membership)
        await self._session.flush()
        return membership

    async def remove_member(
        self, *, team_id: uuid.UUID, actor_user_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """Remove a member. Only an admin may remove; the owner cannot be removed."""
        team = await self.get_team(team_id)
        await self._require_admin(team_id, actor_user_id)
        if user_id == team.owner_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="The team owner cannot be removed."
            )
        membership = await self._membership(team_id, user_id)
        if membership is None:
            return False
        await self._session.delete(membership)
        await self._session.flush()
        return True

    async def list_members(self, team_id: uuid.UUID) -> Sequence[TeamMembership]:
        stmt = select(TeamMembership).where(TeamMembership.team_id == team_id)
        return (await self._session.execute(stmt)).scalars().all()

    async def get_user_team_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(TeamMembership.team_id).where(TeamMembership.user_id == user_id)
        return [row[0] for row in (await self._session.execute(stmt)).all()]

    async def is_member(self, team_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        return (await self._membership(team_id, user_id)) is not None

    async def is_admin(self, team_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        m = await self._membership(team_id, user_id)
        return m is not None and m.role == "admin"

    # ── internals ───────────────────────────────────────────────
    async def _membership(self, team_id: uuid.UUID, user_id: uuid.UUID) -> TeamMembership | None:
        stmt = select(TeamMembership).where(
            and_(TeamMembership.team_id == team_id, TeamMembership.user_id == user_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def _require_admin(self, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
        if not await self.is_admin(team_id, user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only a team admin can perform this action.",
            )

    async def require_member(self, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
        if not await self.is_member(team_id, user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this team.",
            )
