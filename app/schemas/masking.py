"""Data masking schemas — request/response models for masking endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import OrmBase


class MaskingTestRequest(BaseModel):
    """Request body for the /masking/test endpoint."""

    text: str = Field(..., description="Text to scan for PII patterns")


class MaskingTestResponse(BaseModel):
    """Response from the /masking/test endpoint."""

    original_text: str
    masked_text: str
    was_modified: bool
    patterns_detected: list[str]
    detection_count: int


class MaskingLogResponse(OrmBase):
    """Single masking audit log entry."""

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    field_name: str
    patterns_detected: list[str]
    detection_count: int
    original_content_hash: str | None = None
    user_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    created_at: datetime


class MaskingConfigResponse(BaseModel):
    """Current data masking configuration."""

    enabled: bool
    active_patterns: list[str]
    log_detections: bool
    custom_patterns_configured: bool


class MaskingStatsResponse(BaseModel):
    """Aggregate masking statistics."""

    total_masking_actions: int
    by_entity_type: dict[str, int]
    masking_enabled: bool
    active_patterns: list[str]
