"""Observation schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import OrmBase
from app.schemas.memory import MemoryResponse


class ObservationCreate(BaseModel):
    event_id: uuid.UUID
    run_id: uuid.UUID
    user_id: uuid.UUID
    content: str
    observation_type: str | None = None
    source_type: str = "system_inference"
    # Trust domain this candidate arrived from; carried onto the memory when
    # the observation is promoted.
    origin: str = "agent_inference"
    origin_ref: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: dict[str, Any] | None = None


class ObservationExtractRequest(BaseModel):
    """Request body for rule-based extraction from an event."""

    event_id: uuid.UUID


class ObservationPromoteRequest(BaseModel):
    """Promote a candidate observation into a canonical memory.

    The observation's content becomes the memory content; provenance
    (event/observation/run) is carried onto the memory automatically.
    """

    memory_key: str
    memory_type: str = "semantic"  # MemoryType value
    layer: str = "atom"  # MemoryLayer value
    scope: str = "user"  # MemoryScope value
    project_id: uuid.UUID | None = None
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    authority_level: int = Field(default=1, ge=1, le=4)
    # Override the observation's confidence; defaults to the observation's own.
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_contradiction: bool = False
    # Override the observation's origin; defaults to the observation's own.
    origin: str | None = None
    # Mark the resulting memory as human-verified provenance.
    human_verified: bool = False


class ObservationRejectRequest(BaseModel):
    reason: str | None = None


class ObservationResponse(OrmBase):
    id: uuid.UUID
    event_id: uuid.UUID
    run_id: uuid.UUID
    user_id: uuid.UUID
    content: str
    observation_type: str | None = None
    source_type: str
    origin: str = "agent_inference"
    origin_ref: str | None = None
    confidence: float
    metadata: dict[str, Any] | None = None
    status: str
    memory_id: uuid.UUID | None = None
    created_at: datetime


class ObservationPromoteResponse(BaseModel):
    """Result of promoting an observation: the observation plus its memory."""

    observation: ObservationResponse
    memory: MemoryResponse
    memory_created: bool
