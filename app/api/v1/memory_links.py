"""Memory link endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.memory_link import MemoryLinkCreate, MemoryLinkResponse
from app.services.memory_service import MemoryService

router = APIRouter()


@router.post("", response_model=MemoryLinkResponse, status_code=201)
async def create_memory_link(
    data: MemoryLinkCreate,
    session: AsyncSession = Depends(get_session),
) -> MemoryLinkResponse:
    svc = MemoryService(session)
    link = await svc.create_link(
        source_memory_id=data.source_memory_id,
        target_memory_id=data.target_memory_id,
        link_type=data.link_type,
        description=data.description,
    )
    return MemoryLinkResponse.model_validate(link)
