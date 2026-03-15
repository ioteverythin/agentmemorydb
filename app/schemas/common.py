"""Shared schema primitives."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TimestampMixin(BaseModel):
    created_at: datetime
    updated_at: datetime | None = None


class OrmBase(BaseModel):
    """Base for models read from ORM objects."""

    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    """Standard error response body."""

    detail: str


class IDResponse(OrmBase):
    """Generic response containing just an ID."""

    id: uuid.UUID
