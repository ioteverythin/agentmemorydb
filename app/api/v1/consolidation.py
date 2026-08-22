"""Consolidation endpoints — duplicate merging and sleep-time reflection."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import enforce_tenant, get_current_api_key
from app.db.session import get_session
from app.models.api_key import APIKey
from app.schemas.consolidation import ConsolidationRunResponse
from app.schemas.memory import MemoryResponse
from app.services.consolidation_service import ConsolidationService
from app.services.reflection_service import ReflectionService

router = APIRouter()


class MergeRequest(BaseModel):
    keep_id: uuid.UUID
    archive_id: uuid.UUID
    reason: str = "Consolidated as duplicate"


class DuplicateGroup(BaseModel):
    content_hash: str
    count: int
    memory_ids: list[uuid.UUID]
    memory_keys: list[str]


class AutoConsolidateResponse(BaseModel):
    duplicate_groups_found: int
    memories_merged: int


@router.get("/duplicates", response_model=list[DuplicateGroup])
async def find_duplicates(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[DuplicateGroup]:
    """Find groups of exact-duplicate memories for a user."""
    svc = ConsolidationService(session)
    groups = await svc.find_exact_duplicates(user_id)
    return [
        DuplicateGroup(
            content_hash=group[0].content_hash,
            count=len(group),
            memory_ids=[m.id for m in group],
            memory_keys=[m.memory_key for m in group],
        )
        for group in groups
    ]


@router.post("/merge", response_model=MemoryResponse)
async def merge_memories(
    data: MergeRequest,
    session: AsyncSession = Depends(get_session),
) -> MemoryResponse:
    """Merge two memories: keep one, archive the other, create link."""
    svc = ConsolidationService(session)
    kept = await svc.merge_memories(
        keep_id=data.keep_id,
        archive_id=data.archive_id,
        reason=data.reason,
    )
    return MemoryResponse.model_validate(kept)


@router.post("/auto", response_model=AutoConsolidateResponse)
async def auto_consolidate(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> AutoConsolidateResponse:
    """Automatically find and merge exact-duplicate memories."""
    svc = ConsolidationService(session)
    result = await svc.auto_consolidate(user_id)
    return AutoConsolidateResponse(**result)


# ── Sleep-time consolidation (reflection) ───────────────────────


@router.get("/runs", response_model=list[ConsolidationRunResponse])
async def list_consolidation_runs(
    user_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    api_key: APIKey | None = Depends(get_current_api_key),
) -> list[ConsolidationRunResponse]:
    """Reflection pass history, newest first.

    ``status="skipped"`` with ``skipped_reason="no_llm_provider"`` is the row to
    look for when reflection appears to be doing nothing: it means the feature is
    on but has no model to think with.
    """
    enforce_tenant(api_key, user_id)
    runs = await ReflectionService(session).list_runs(user_id=user_id, limit=limit, offset=offset)
    return [ConsolidationRunResponse.model_validate(r) for r in runs]


@router.post("/reflect", response_model=ConsolidationRunResponse)
async def run_reflection(
    user_id: uuid.UUID,
    project_id: uuid.UUID | None = Query(default=None),
    dry_run: bool = Query(
        default=False, description="Cluster and report without calling the LLM or writing."
    ),
    session: AsyncSession = Depends(get_session),
    api_key: APIKey | None = Depends(get_current_api_key),
) -> ConsolidationRunResponse:
    """Run a reflection pass now for one user.

    Returns the run record whether or not it produced anything — a skip is a
    result, and its ``skipped_reason`` says which one.
    """
    enforce_tenant(api_key, user_id)
    run = await ReflectionService(session).reflect(user_id, project_id=project_id, dry_run=dry_run)
    return ConsolidationRunResponse.model_validate(run)
