"""Distillation & forgetting endpoints — maintain the memory pyramid."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import enforce_tenant, get_current_api_key
from app.db.session import get_session
from app.models.api_key import APIKey
from app.services.distillation_service import DistillationService
from app.services.forgetting_service import ForgettingService

router = APIRouter()


class DistillRequest(BaseModel):
    user_id: uuid.UUID
    project_id: uuid.UUID | None = None
    # Preview what would be produced without writing anything.
    dry_run: bool = False


@router.post("/run")
async def run_distillation(
    data: DistillRequest,
    session: AsyncSession = Depends(get_session),
    api_key: APIKey | None = Depends(get_current_api_key),
) -> dict:
    """Roll a user's atoms up the pyramid into scenario and persona layers.

    Idempotent: re-running updates the same ``scenario:<topic>`` and
    ``persona:core`` keys (creating versioned snapshots). Use ``dry_run`` to
    preview the scenarios that would be produced without writing.
    """
    enforce_tenant(api_key, data.user_id)
    svc = DistillationService(session)
    return await svc.distill(data.user_id, project_id=data.project_id, dry_run=data.dry_run)


class ForgetRequest(BaseModel):
    dry_run: bool = True  # default to preview — archival is destructive


@router.post("/forget")
async def run_forgetting(
    data: ForgetRequest,
    session: AsyncSession = Depends(get_session),
    api_key: APIKey | None = Depends(get_current_api_key),
) -> dict:
    """Archive low-retention memories (recency × importance × access-aware).

    Distilled layers (persona, scenario) are exempt. Defaults to ``dry_run`` so
    you can see how many memories would be archived before committing.
    """
    svc = ForgettingService(session)
    return await svc.archive_low_retention(dry_run=data.dry_run)
