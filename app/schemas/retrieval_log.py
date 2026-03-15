"""RetrievalLog schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.common import OrmBase


class RetrievalLogCreate(BaseModel):
    run_id: uuid.UUID | None = None
    user_id: uuid.UUID
    strategy: str = "hybrid"
    filters_json: dict[str, Any] | None = None
    query_text: str | None = None
    top_k: int = 10
    total_candidates: int = 0
    items: list[RetrievalLogItemCreate] | None = None


class RetrievalLogItemCreate(BaseModel):
    memory_id: uuid.UUID
    rank: int
    final_score: float
    vector_score: float | None = None
    recency_score: float | None = None
    importance_score: float | None = None
    authority_score: float | None = None
    confidence_score: float | None = None
    selected_for_prompt: bool = False


class RetrievalLogItemResponse(OrmBase):
    id: uuid.UUID
    retrieval_log_id: uuid.UUID
    memory_id: uuid.UUID
    rank: int
    final_score: float
    vector_score: float | None = None
    recency_score: float | None = None
    importance_score: float | None = None
    authority_score: float | None = None
    confidence_score: float | None = None
    selected_for_prompt: bool
    created_at: datetime


class RetrievalLogResponse(OrmBase):
    id: uuid.UUID
    run_id: uuid.UUID | None = None
    user_id: uuid.UUID
    strategy: str
    filters_json: dict[str, Any] | None = None
    query_text: str | None = None
    top_k: int
    total_candidates: int
    items: list[RetrievalLogItemResponse] = []
    created_at: datetime
