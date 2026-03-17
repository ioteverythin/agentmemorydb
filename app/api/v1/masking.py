"""Data masking endpoints — configuration, testing, audit logs."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.db.session import get_session
from app.schemas.masking import (
    MaskingConfigResponse,
    MaskingLogResponse,
    MaskingStatsResponse,
    MaskingTestRequest,
    MaskingTestResponse,
)
from app.services.masking_service import MaskingService
from app.utils.masking import get_default_engine

router = APIRouter()


@router.get("/config", response_model=MaskingConfigResponse)
async def get_masking_config() -> MaskingConfigResponse:
    """Return current data masking configuration."""
    engine = get_default_engine()
    return MaskingConfigResponse(
        enabled=settings.enable_data_masking,
        active_patterns=engine.active_patterns,
        log_detections=settings.masking_log_detections,
        custom_patterns_configured=bool(settings.masking_custom_patterns),
    )


@router.post("/test", response_model=MaskingTestResponse)
async def test_masking(data: MaskingTestRequest) -> MaskingTestResponse:
    """Dry-run masking on arbitrary text — nothing is persisted.

    Useful for verifying pattern configuration before enabling masking
    in production.
    """
    engine = get_default_engine()
    result = engine.mask_text(data.text)
    return MaskingTestResponse(
        original_text=result.original_text,
        masked_text=result.masked_text,
        was_modified=result.was_modified,
        patterns_detected=result.patterns_detected,
        detection_count=len(result.detections),
    )


@router.get("/logs", response_model=list[MaskingLogResponse])
async def list_masking_logs(
    entity_type: str | None = Query(
        None, description="Filter by entity type (memory, event, observation)"
    ),
    user_id: uuid.UUID | None = Query(None, description="Filter by user ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[MaskingLogResponse]:
    """List masking audit log entries."""
    svc = MaskingService(session)
    logs = await svc.list_logs(
        entity_type=entity_type,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    return [MaskingLogResponse.model_validate(log) for log in logs]


@router.get("/stats", response_model=MaskingStatsResponse)
async def get_masking_stats(
    session: AsyncSession = Depends(get_session),
) -> MaskingStatsResponse:
    """Return aggregate masking statistics."""
    svc = MaskingService(session)
    stats = await svc.get_stats()
    return MaskingStatsResponse(**stats)
