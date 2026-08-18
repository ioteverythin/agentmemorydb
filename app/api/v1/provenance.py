"""Provenance endpoints — trust policy inspection and the quarantine queue."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import enforce_tenant, get_current_api_key
from app.core.config import settings
from app.db.session import get_session
from app.models.api_key import APIKey
from app.schemas.memory import MemoryResponse
from app.schemas.provenance import OriginPolicyResponse, QuarantineReviewRequest
from app.services.memory_service import MemoryService
from app.utils.provenance import AUTHORITY_CEILINGS, UNTRUSTED_ORIGINS

router = APIRouter()


@router.get("/policy", response_model=OriginPolicyResponse)
async def get_origin_policy() -> OriginPolicyResponse:
    """The active trust policy: authority ceilings and quarantine rules.

    Useful for a writer to know, before it writes, what authority it can claim.
    """
    return OriginPolicyResponse(
        enabled=settings.enable_poisoning_resistance,
        quarantine_confidence_threshold=settings.quarantine_confidence_threshold,
        authority_ceilings={str(k): v for k, v in AUTHORITY_CEILINGS.items()},
        untrusted_origins=sorted(str(o) for o in UNTRUSTED_ORIGINS),
    )


@router.get("/quarantine", response_model=list[MemoryResponse])
async def list_quarantined(
    user_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    api_key: APIKey | None = Depends(get_current_api_key),
) -> list[MemoryResponse]:
    """The review queue — writes held back because their origin was untrusted."""
    enforce_tenant(api_key, user_id)
    memories = await MemoryService(session).list_quarantined(
        user_id=user_id, limit=limit, offset=offset
    )
    return [MemoryResponse.model_validate(m) for m in memories]


@router.post("/quarantine/{memory_id}/review", response_model=MemoryResponse)
async def review_quarantined(
    memory_id: uuid.UUID,
    data: QuarantineReviewRequest,
    session: AsyncSession = Depends(get_session),
    api_key: APIKey | None = Depends(get_current_api_key),
) -> MemoryResponse:
    """Approve a quarantined memory into active recall, or reject it.

    Approval is the only route out of quarantine: the system held the write back
    precisely because it could not vouch for the writer, so a human decides.
    Rejection retracts the memory — it stays queryable for audit but is never
    retrieved.
    """
    svc = MemoryService(session)
    memory = await svc.get_memory(memory_id)
    enforce_tenant(api_key, memory.user_id)
    memory = await svc.release_quarantine(memory_id, approve=data.approve, reviewer=data.reviewer)
    return MemoryResponse.model_validate(memory)
