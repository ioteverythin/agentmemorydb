"""Event schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.common import OrmBase


class EventCreate(BaseModel):
    run_id: uuid.UUID
    user_id: uuid.UUID
    event_type: str
    content: str | None = None
    payload: dict[str, Any] | None = None
    source: str | None = None
    sequence_number: int | None = None


class EventResponse(OrmBase):
    id: uuid.UUID
    run_id: uuid.UUID
    user_id: uuid.UUID
    event_type: str
    content: str | None = None
    payload: dict[str, Any] | None = None
    source: str | None = None
    sequence_number: int | None = None
    created_at: datetime
