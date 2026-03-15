"""Bulk operation endpoints — batch upsert and batch search."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.memory import MemoryResponse, MemorySearchRequest, MemorySearchResponse, MemoryUpsert
from app.services.memory_service import MemoryService
from app.services.retrieval_service import RetrievalService

router = APIRouter()


# ── Batch Upsert ────────────────────────────────────────────────

class BatchUpsertRequest(BaseModel):
    memories: list[MemoryUpsert] = Field(..., min_length=1, max_length=100)


class BatchUpsertResult(BaseModel):
    memory: MemoryResponse
    is_new: bool


class BatchUpsertResponse(BaseModel):
    results: list[BatchUpsertResult]
    total: int
    created: int
    updated: int


@router.post("/upsert", response_model=BatchUpsertResponse)
async def batch_upsert(
    data: BatchUpsertRequest,
    session: AsyncSession = Depends(get_session),
) -> BatchUpsertResponse:
    """Upsert up to 100 memories in a single request.

    Each memory follows the same upsert logic as the single endpoint:
    content-hash dedup, version snapshots, contradiction handling.
    """
    svc = MemoryService(session)
    results: list[BatchUpsertResult] = []
    created = 0
    updated = 0

    for item in data.memories:
        memory, is_new = await svc.upsert(item)
        results.append(
            BatchUpsertResult(
                memory=MemoryResponse.model_validate(memory),
                is_new=is_new,
            )
        )
        if is_new:
            created += 1
        else:
            updated += 1

    return BatchUpsertResponse(
        results=results,
        total=len(results),
        created=created,
        updated=updated,
    )


# ── Batch Search ────────────────────────────────────────────────

class BatchSearchRequest(BaseModel):
    queries: list[MemorySearchRequest] = Field(..., min_length=1, max_length=20)


class BatchSearchResponse(BaseModel):
    results: list[MemorySearchResponse]
    total_queries: int


@router.post("/search", response_model=BatchSearchResponse)
async def batch_search(
    data: BatchSearchRequest,
    session: AsyncSession = Depends(get_session),
) -> BatchSearchResponse:
    """Execute up to 20 search queries in a single request.

    Each query runs independently with its own filters and scoring.
    """
    svc = RetrievalService(session)
    results: list[MemorySearchResponse] = []

    for query in data.queries:
        result = await svc.search(query)
        results.append(result)

    return BatchSearchResponse(
        results=results,
        total_queries=len(results),
    )
