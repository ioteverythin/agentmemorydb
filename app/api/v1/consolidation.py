"""Consolidation endpoints — detect and merge duplicate memories."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.memory import MemoryResponse
from app.services.consolidation_service import ConsolidationService

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
