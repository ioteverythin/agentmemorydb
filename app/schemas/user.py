"""User schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import OrmBase


class UserCreate(BaseModel):
    name: str
    email: str | None = None
    external_id: str | None = None


class UserResponse(OrmBase):
    id: uuid.UUID
    name: str
    email: str | None = None
    external_id: str | None = None
    created_at: datetime
