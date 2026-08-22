"""Forgetting endpoints — the audit trail and manual job triggers."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import enforce_tenant, get_current_api_key
from app.db.session import get_session
from app.models.api_key import APIKey
from app.schemas.forgetting import ForgettingLogResponse
from app.services.forgetting_service import ForgettingService

router = APIRouter()


@router.get("/log", response_model=list[ForgettingLogResponse])
async def list_forgetting_log(
    user_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    api_key: APIKey | None = Depends(get_current_api_key),
) -> list[ForgettingLogResponse]:
    """Every forgetting decision, newest first — decay, expiry, and erasure.

    This is the answer to "where did that memory go?". Erasure rows keep only a
    content hash, which is what makes the deletion auditable without retaining
    the erased content.
    """
    enforce_tenant(api_key, user_id)
    entries = await ForgettingService(session).list_log(user_id=user_id, limit=limit, offset=offset)
    return [ForgettingLogResponse.model_validate(e) for e in entries]


@router.post("/decay")
async def run_decay(
    dry_run: bool = Query(default=True, description="Report what would decay without writing."),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Run importance decay now (defaults to a dry run)."""
    return await ForgettingService(session).decay_importance(dry_run=dry_run)


@router.post("/archive")
async def run_archive(
    dry_run: bool = Query(default=True, description="Report what would archive without writing."),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Run retention-based archival now (defaults to a dry run)."""
    return await ForgettingService(session).archive_low_retention(dry_run=dry_run)
