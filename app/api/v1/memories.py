"""Memory endpoints — upsert, search, status, versions, links."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.memory import (
    MemoryResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryStatusUpdate,
    MemoryUpsert,
    MemoryVersionResponse,
)
from app.schemas.memory_link import MemoryLinkResponse
from app.services.memory_service import MemoryService
from app.services.retrieval_service import RetrievalService

router = APIRouter()


@router.post("/upsert", response_model=MemoryResponse, status_code=200)
async def upsert_memory(
    data: MemoryUpsert,
    session: AsyncSession = Depends(get_session),
) -> MemoryResponse:
    """Create or update a canonical memory.

    If an active memory with the same ``memory_key`` already exists for the
    user/scope/project, the previous state is snapshotted and the canonical
    record is updated.  If ``is_contradiction`` is True, conflict links are
    created automatically.
    """
    svc = MemoryService(session)
    memory, _is_new = await svc.upsert(data)
    return MemoryResponse.model_validate(memory)


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> MemoryResponse:
    svc = MemoryService(session)
    memory = await svc.get_memory(memory_id)
    return MemoryResponse.model_validate(memory)


@router.post("/search", response_model=MemorySearchResponse)
async def search_memories(
    data: MemorySearchRequest,
    session: AsyncSession = Depends(get_session),
) -> MemorySearchResponse:
    """Hybrid retrieval endpoint.

    Supports vector similarity (if embedding or query_text provided),
    metadata filtering, and composite scoring with optional score breakdown
    (set ``explain=true``).
    """
    svc = RetrievalService(session)
    return await svc.search(data)


@router.patch("/{memory_id}/status", response_model=MemoryResponse)
async def update_memory_status(
    memory_id: uuid.UUID,
    data: MemoryStatusUpdate,
    session: AsyncSession = Depends(get_session),
) -> MemoryResponse:
    svc = MemoryService(session)
    memory = await svc.update_status(memory_id, data)
    return MemoryResponse.model_validate(memory)


@router.get("", response_model=list[MemoryResponse])
async def list_memories(
    user_id: Optional[uuid.UUID] = Query(default=None),
    project_id: Optional[uuid.UUID] = Query(default=None),
    memory_type: Optional[str] = Query(default=None),
    scope: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[MemoryResponse]:
    svc = MemoryService(session)
    memories = await svc.list_memories(
        user_id=user_id,
        project_id=project_id,
        memory_type=memory_type,
        scope=scope,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [MemoryResponse.model_validate(m) for m in memories]


@router.get("/{memory_id}/versions", response_model=list[MemoryVersionResponse])
async def list_memory_versions(
    memory_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[MemoryVersionResponse]:
    svc = MemoryService(session)
    versions = await svc.get_versions(memory_id)
    return [MemoryVersionResponse.model_validate(v) for v in versions]


@router.get("/{memory_id}/links", response_model=list[MemoryLinkResponse])
async def list_memory_links(
    memory_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[MemoryLinkResponse]:
    svc = MemoryService(session)
    links = await svc.get_links(memory_id)
    return [MemoryLinkResponse.model_validate(link) for link in links]
