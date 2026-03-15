"""Task schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.common import OrmBase


class TaskCreate(BaseModel):
    user_id: uuid.UUID
    project_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    title: str
    description: str | None = None
    priority: int | None = 0
    context: dict[str, Any] | None = None


class TaskTransition(BaseModel):
    to_state: str  # TaskState value
    reason: str | None = None
    triggered_by: str | None = None


class TaskResponse(OrmBase):
    id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    title: str
    description: str | None = None
    state: str
    priority: int | None = None
    context: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
