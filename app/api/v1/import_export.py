"""Import/Export endpoints — bulk data portability."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.import_export_service import ImportExportService

router = APIRouter()


class ImportRequest(BaseModel):
    user_id: uuid.UUID
    data: dict[str, Any]
    strategy: str = Field(
        default="upsert",
        description="Import strategy: 'upsert', 'skip_existing', or 'overwrite'",
    )


class ImportResponse(BaseModel):
    imported: int
    skipped: int
    errors: int


@router.get("/export")
async def export_memories(
    user_id: uuid.UUID,
    include_versions: bool = Query(default=True),
    include_links: bool = Query(default=True),
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Export all memories for a user as a portable JSON payload.

    Includes version history and memory links by default.
    """
    svc = ImportExportService(session)
    return await svc.export_memories(
        user_id=user_id,
        include_versions=include_versions,
        include_links=include_links,
        status=status,
    )


@router.post("/import", response_model=ImportResponse)
async def import_memories(
    data: ImportRequest,
    session: AsyncSession = Depends(get_session),
) -> ImportResponse:
    """Import memories from a previously exported payload.

    Strategies:
    - **upsert**: Standard upsert with content-hash dedup
    - **skip_existing**: Skip if a memory with the same key exists
    - **overwrite**: Always update even if content is identical
    """
    svc = ImportExportService(session)
    result = await svc.import_memories(
        user_id=data.user_id,
        data=data.data,
        strategy=data.strategy,
    )
    return ImportResponse(**result)
