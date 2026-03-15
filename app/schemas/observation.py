"""Observation schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import OrmBase


class ObservationCreate(BaseModel):
    event_id: uuid.UUID
    run_id: uuid.UUID
    user_id: uuid.UUID
    content: str
    observation_type: str | None = None
    source_type: str = "system_inference"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: dict[str, Any] | None = None


class ObservationExtractRequest(BaseModel):
    """Request body for rule-based extraction from an event."""

    event_id: uuid.UUID


class ObservationResponse(OrmBase):
    id: uuid.UUID
    event_id: uuid.UUID
    run_id: uuid.UUID
    user_id: uuid.UUID
    content: str
    observation_type: str | None = None
    source_type: str
    confidence: float
    metadata: dict[str, Any] | None = None
    status: str
    memory_id: uuid.UUID | None = None
    created_at: datetime
