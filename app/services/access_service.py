"""Access service — memory sharing, ACL grants, and the read-visibility filter.

This is the enforcement layer that makes ``scope``/``visibility`` real:
retrieval consults :meth:`accessible_predicate` to decide which memories a
viewer may read beyond their own, and sharing/grants are gated so only an
owner (member of the target team) can widen a memory's audience.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.errors import NotFoundError
from app.models.memory import Memory
from app.models.memory_acl import MemoryACL
from app.services.team_service import TeamService

_VISIBILITIES = {"private", "team", "restricted", "agent"}
_PRINCIPALS = {"user", "agent"}


class AccessService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._teams = TeamService(session)

    # ── Read-visibility predicate (used by retrieval) ───────────
    def accessible_predicate(
        self,
        *,
        viewer_user_id: uuid.UUID,
        team_ids: Sequence[uuid.UUID],
        as_agent_id: str | None,
    ) -> ColumnElement | None:
        """A predicate matching *shared* memories this viewer may read.

        The caller ORs this with ``Memory.user_id == viewer`` — a viewer always
        sees their own memories. Returns ``None`` when nothing extra is
        shareable to this viewer (no teams, no agent), so callers can skip it.
        """
        clauses: list[ColumnElement] = []

        if team_ids:
            clauses.append(and_(Memory.visibility == "team", Memory.team_id.in_(team_ids)))
            if as_agent_id:
                clauses.append(
                    and_(
                        Memory.visibility == "agent",
                        Memory.team_id.in_(team_ids),
                        Memory.agent_id == as_agent_id,
                    )
                )

        acl_conds: list[ColumnElement] = [
            and_(
                MemoryACL.principal_type == "user",
                MemoryACL.principal_id == str(viewer_user_id),
            )
        ]
        if as_agent_id:
            acl_conds.append(
                and_(MemoryACL.principal_type == "agent", MemoryACL.principal_id == as_agent_id)
            )
        acl_subq = select(MemoryACL.memory_id).where(or_(*acl_conds))
        clauses.append(and_(Memory.visibility == "restricted", Memory.id.in_(acl_subq)))

        return or_(*clauses) if clauses else None

    # ── Sharing (owner-gated) ───────────────────────────────────
    async def share_memory(
        self,
        *,
        memory_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        visibility: str,
        team_id: uuid.UUID | None = None,
        agent_id: str | None = None,
    ) -> Memory:
        """Change a memory's visibility. Only the owner may share their memory."""
        if visibility not in _VISIBILITIES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid visibility '{visibility}'.",
            )
        memory = await self._owned_memory(memory_id, actor_user_id)

        if visibility in ("team", "agent", "restricted"):
            if team_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"team_id is required for '{visibility}' visibility.",
                )
            # The owner must belong to the team they are sharing into.
            await self._teams.require_member(team_id, actor_user_id)
        if visibility == "agent" and not agent_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="agent_id is required for 'agent' visibility.",
            )

        memory.visibility = visibility
        if visibility == "private":
            memory.team_id = None
            memory.agent_id = None
        else:
            memory.team_id = team_id
            memory.agent_id = agent_id if visibility == "agent" else None
        return memory

    async def grant(
        self,
        *,
        memory_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        principal_type: str,
        principal_id: str,
    ) -> MemoryACL:
        """Grant a principal read access to a restricted memory (owner-gated)."""
        if principal_type not in _PRINCIPALS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid principal_type '{principal_type}'.",
            )
        await self._owned_memory(memory_id, actor_user_id)

        existing = await self._session.execute(
            select(MemoryACL).where(
                and_(
                    MemoryACL.memory_id == memory_id,
                    MemoryACL.principal_type == principal_type,
                    MemoryACL.principal_id == principal_id,
                )
            )
        )
        found = existing.scalar_one_or_none()
        if found is not None:
            return found

        acl = MemoryACL(
            memory_id=memory_id, principal_type=principal_type, principal_id=principal_id
        )
        self._session.add(acl)
        await self._session.flush()
        return acl

    async def revoke(
        self,
        *,
        memory_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        principal_type: str,
        principal_id: str,
    ) -> bool:
        await self._owned_memory(memory_id, actor_user_id)
        row = await self._session.execute(
            select(MemoryACL).where(
                and_(
                    MemoryACL.memory_id == memory_id,
                    MemoryACL.principal_type == principal_type,
                    MemoryACL.principal_id == principal_id,
                )
            )
        )
        acl = row.scalar_one_or_none()
        if acl is None:
            return False
        await self._session.delete(acl)
        await self._session.flush()
        return True

    async def list_grants(self, memory_id: uuid.UUID) -> Sequence[MemoryACL]:
        return (
            (await self._session.execute(select(MemoryACL).where(MemoryACL.memory_id == memory_id)))
            .scalars()
            .all()
        )

    # ── internals ───────────────────────────────────────────────
    async def _owned_memory(self, memory_id: uuid.UUID, actor_user_id: uuid.UUID) -> Memory:
        memory = await self._session.get(Memory, memory_id)
        if memory is None:
            raise NotFoundError("Memory", memory_id)
        if memory.user_id != actor_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the owner can change sharing for this memory.",
            )
        return memory
