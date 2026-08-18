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
    layer: str = "atom"  # MemoryLayer value: raw | atom | scenario | persona
    content: str
    embedding: list[float] | None = None
    payload: dict[str, Any] | None = None
    source_type: str = "system_inference"
    # Trust domain of the writer (MemoryOrigin). Caps the authority this write
    # may claim and decides quarantine eligibility when poisoning resistance is
    # on. Defaults to `agent_inference` — what an unattributed write is.
    origin: str = "agent_inference"
    # Pointer to the specific writer: a URL, tool name, or document id.
    origin_ref: str | None = None
    source_event_id: uuid.UUID | None = None
    source_observation_id: uuid.UUID | None = None
    source_run_id: uuid.UUID | None = None
    authority_level: int = Field(default=1, ge=1, le=4)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    # Pin a memory to exempt it from importance decay and retention archival.
    # ``None`` leaves an existing memory's pin state untouched.
    pinned: bool | None = None
    # World-validity: when this fact became true. Agents may backdate
    # ("the user moved to Pune last March"). Defaults to now().
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    expires_at: datetime | None = None
    # Close the current fact's validity window *without* a replacement — the
    # fact simply stopped being true. Content fields are ignored.
    invalidate_only: bool = False
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
    layers: list[str] | None = None  # MemoryLayer values to include
    status: str = "active"
    top_k: int = Field(default=10, ge=1, le=100)
    min_confidence: float | None = None
    min_importance: float | None = None
    metadata_filter: dict[str, Any] | None = None
    include_expired: bool = False
    explain: bool = False
    # Fuse dense (vector) and sparse (full-text/BM25) rankings via RRF when a
    # query_text is present and the backend supports full-text search.
    use_fulltext: bool = True
    # Also retrieve memories shared to this viewer (team / restricted / agent),
    # not just their own. Off by default so single-user behaviour is unchanged.
    include_shared: bool = False
    # Agent this viewer is acting as (for agent-bound "loadout" memories).
    as_agent_id: str | None = None
    # Point-in-time query: return the fact generations valid at this instant
    # ("what did the agent believe at T?"). Omit for current facts.
    as_of: datetime | None = None
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
    # Populated only when RRF fusion runs: the memory's fused reciprocal-rank
    # score across the vector and full-text rankings.
    rrf_score: float | None = None


# ── Responses ───────────────────────────────────────────────────
class MemoryResponse(OrmBase):
    id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID | None = None
    memory_key: str
    memory_type: str
    scope: str
    layer: str = "atom"
    visibility: str = "private"
    team_id: uuid.UUID | None = None
    agent_id: str | None = None
    content: str
    content_hash: str
    payload: dict[str, Any] | None = None
    source_type: str
    origin: str = "agent_inference"
    origin_ref: str | None = None
    source_event_id: uuid.UUID | None = None
    source_observation_id: uuid.UUID | None = None
    source_run_id: uuid.UUID | None = None
    status: str
    pinned: bool = False
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


class MemoryPinRequest(BaseModel):
    """Pin or unpin a memory (pinned memories never decay or auto-archive)."""

    pinned: bool


class MemoryInvalidateRequest(BaseModel):
    """Close a fact's world-validity window with no replacement."""

    # When the fact stopped being true. Defaults to now().
    valid_to: datetime | None = None
    reason: str | None = None


# ── Context assembly (LLM-ready, budget-capped, injection-safe) ─────
class ContextAssembleRequest(BaseModel):
    """Assemble a budget-capped, layer-ordered memory context block."""

    user_id: uuid.UUID
    project_id: uuid.UUID | None = None
    query_text: str | None = None
    embedding: list[float] | None = None
    layers: list[str] | None = None  # default: all layers
    scopes: list[str] | None = None
    top_k: int = Field(default=20, ge=1, le=100)
    # Budgets — assembly stops once either is exceeded.
    max_items: int = Field(default=20, ge=1, le=100)
    char_budget: int = Field(default=6000, ge=100, le=100_000)
    # Max characters kept from any single memory before truncation.
    per_item_max_chars: int = Field(default=2000, ge=50, le=20_000)
    min_confidence: float | None = None
    min_importance: float | None = None
    use_fulltext: bool = True
    # Assemble the context as it stood at this instant.
    as_of: datetime | None = None
    run_id: uuid.UUID | None = None


class AssembledMemory(BaseModel):
    memory_id: uuid.UUID
    memory_key: str
    layer: str
    memory_type: str
    final_score: float
    included: bool
    chars: int


class ContextAssembleResponse(BaseModel):
    """The assembled context plus an accounting of what was included."""

    context: str  # ready to inject into a system/user prompt
    strategy: str
    total_candidates: int
    included_count: int
    char_count: int
    token_estimate: int  # rough (chars / 4)
    truncated: bool  # True if budgets cut off candidates
    items: list[AssembledMemory]


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
