"""Schemas for teams, memberships, memory sharing, and ACL grants."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import OrmBase


# ── Teams ───────────────────────────────────────────────────────
class TeamCreate(BaseModel):
    name: str
    owner_user_id: uuid.UUID


class TeamResponse(OrmBase):
    id: uuid.UUID
    name: str
    owner_user_id: uuid.UUID
    created_at: datetime


class MemberAddRequest(BaseModel):
    actor_user_id: uuid.UUID  # must be a team admin
    user_id: uuid.UUID
    role: str = "member"  # admin | member


class MemberRemoveRequest(BaseModel):
    actor_user_id: uuid.UUID


class MemberResponse(OrmBase):
    id: uuid.UUID
    team_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    created_at: datetime


# ── Sharing / ACL ───────────────────────────────────────────────
class MemoryShareRequest(BaseModel):
    actor_user_id: uuid.UUID  # must own the memory
    visibility: str  # private | team | restricted | agent
    team_id: uuid.UUID | None = None
    agent_id: str | None = None


class ACLGrantRequest(BaseModel):
    actor_user_id: uuid.UUID
    principal_type: str  # user | agent
    principal_id: str


class ACLResponse(OrmBase):
    id: uuid.UUID
    memory_id: uuid.UUID
    principal_type: str
    principal_id: str
    created_at: datetime
