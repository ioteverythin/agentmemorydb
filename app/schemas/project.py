"""Project schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import OrmBase


class ProjectCreate(BaseModel):
    user_id: uuid.UUID
    name: str
    description: str | None = None


class ProjectResponse(OrmBase):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: str | None = None
    created_at: datetime
