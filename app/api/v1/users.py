"""User endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import assert_scope, enforce_tenant, get_current_api_key
from app.db.session import get_session
from app.models.api_key import APIKey
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.forgetting import ErasureResponse
from app.schemas.user import UserCreate, UserResponse
from app.services.forgetting_service import ForgettingService

router = APIRouter()


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    data: UserCreate,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    repo = UserRepository(session)
    user = User(name=data.name, email=data.email, external_id=data.external_id)
    user = await repo.create(user)
    return UserResponse.model_validate(user)


@router.delete("/{user_id}/memories", response_model=ErasureResponse)
async def delete_user_memories(
    user_id: uuid.UUID,
    mode: str = Query(
        default="erase",
        pattern="^erase$",
        description="Only 'erase' is supported — this endpoint exists for erasure requests.",
    ),
    reason: str | None = Query(default=None, description="Recorded in the forgetting log."),
    session: AsyncSession = Depends(get_session),
    api_key: APIKey | None = Depends(get_current_api_key),
) -> ErasureResponse:
    """Erase every memory belonging to a user (GDPR right-to-be-forgotten).

    Irreversible. Requires an API key with the ``erase`` scope. One
    ``forgetting_log`` tombstone is written per erased memory, each carrying the
    SHA-256 of the content that was removed, so the erasure is provable without
    the data surviving.
    """
    enforce_tenant(api_key, user_id)
    assert_scope(api_key, "erase", allow_unscoped=False)
    report = await ForgettingService(session).erase_user_memories(
        user_id,
        action="user_erasure",
        reason=reason,
        triggered_by="api:delete_user_memories",
    )
    return ErasureResponse(erased=report["erased"], action=report["action"], user_id=user_id)
