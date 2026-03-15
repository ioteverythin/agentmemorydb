"""Retrieval log endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.retrieval_log import RetrievalLogCreate, RetrievalLogResponse
from app.services.retrieval_log_service import RetrievalLogService

router = APIRouter()


@router.post("", response_model=RetrievalLogResponse, status_code=201)
async def create_retrieval_log(
    data: RetrievalLogCreate,
    session: AsyncSession = Depends(get_session),
) -> RetrievalLogResponse:
    svc = RetrievalLogService(session)
    log = await svc.create_log(data)
    return RetrievalLogResponse.model_validate(log)
