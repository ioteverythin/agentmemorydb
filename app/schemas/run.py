"""AgentRun schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.common import OrmBase


class RunCreate(BaseModel):
    user_id: uuid.UUID
    project_id: uuid.UUID | None = None
    agent_name: str | None = None
    context: dict[str, Any] | None = None


class RunComplete(BaseModel):
    summary: str | None = None


class RunResponse(OrmBase):
    id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID | None = None
    agent_name: str | None = None
    status: str
    context: dict[str, Any] | None = None
    summary: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
