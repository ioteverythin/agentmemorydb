"""Memory schemas — upsert, search, response, score breakdown."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import OrmBase


# ── Upsert ──────────────────────────────────────────────────────
class MemoryUpsert(BaseModel):
    """Create or update a canonical memory record."""

    user_id: uuid.UUID
    project_id: uuid.UUID | None = None
    memory_key: str
    memory_type: str  # MemoryType value
    scope: str = "user"  # MemoryScope value
    content: str
    embedding: list[float] | None = None
    payload: dict[str, Any] | None = None
    source_type: str = "system_inference"
    source_event_id: uuid.UUID | None = None
    source_observation_id: uuid.UUID | None = None
    source_run_id: uuid.UUID | None = None
    authority_level: int = Field(default=1, ge=1, le=4)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    expires_at: datetime | None = None
    # Conflict handling
    is_contradiction: bool = False


# ── Search ──────────────────────────────────────────────────────
class MemorySearchRequest(BaseModel):
    """Hybrid search request for memories."""

    user_id: uuid.UUID
    project_id: uuid.UUID | None = None
    query_text: str | None = None
    embedding: list[float] | None = None
    memory_types: list[str] | None = None
    scopes: list[str] | None = None
    status: str = "active"
    top_k: int = Field(default=10, ge=1, le=100)
    min_confidence: float | None = None
    min_importance: float | None = None
    metadata_filter: dict[str, Any] | None = None
    include_expired: bool = False
    explain: bool = False
    # Optional: attach to a retrieval log
    run_id: uuid.UUID | None = None


# ── Score breakdown ─────────────────────────────────────────────
class ScoreBreakdown(BaseModel):
    vector_score: float | None = None
    recency_score: float
    importance_score: float
    authority_score: float
    confidence_score: float
    final_score: float


# ── Responses ───────────────────────────────────────────────────
class MemoryResponse(OrmBase):
    id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID | None = None
    memory_key: str
    memory_type: str
    scope: str
    content: str
    content_hash: str
    payload: dict[str, Any] | None = None
    source_type: str
    source_event_id: uuid.UUID | None = None
    source_observation_id: uuid.UUID | None = None
    source_run_id: uuid.UUID | None = None
    status: str
    authority_level: int
    confidence: float
    importance_score: float
    recency_score: float
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    expires_at: datetime | None = None
    last_verified_at: datetime | None = None
    version: int
    created_at: datetime
    updated_at: datetime


class MemorySearchResult(BaseModel):
    memory: MemoryResponse
    score: ScoreBreakdown | None = None


class MemorySearchResponse(BaseModel):
    results: list[MemorySearchResult]
    total_candidates: int
    strategy: str


class MemoryStatusUpdate(BaseModel):
    status: str  # MemoryStatus value


class MemoryVersionResponse(OrmBase):
    id: uuid.UUID
    memory_id: uuid.UUID
    version: int
    content: str
    content_hash: str
    payload: dict[str, Any] | None = None
    confidence: float
    importance_score: float
    source_type: str
    status: str
    created_at: datetime
    superseded_at: datetime
