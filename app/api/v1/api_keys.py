"""API-key management endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import generate_api_key
from app.db.session import get_session
from app.models.api_key import APIKey
from app.schemas.common import OrmBase

router = APIRouter()


class APIKeyCreate(BaseModel):
    user_id: uuid.UUID
    name: str
    scopes: str | None = Field(default="*", description="Comma-separated scopes, or '*' for all")
    expires_at: datetime | None = None


class APIKeyResponse(OrmBase):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    key_prefix: str
    scopes: str | None
    is_active: bool
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class APIKeyCreatedResponse(APIKeyResponse):
    """Returned only on creation — includes the raw key (shown once)."""

    raw_key: str


@router.post("", response_model=APIKeyCreatedResponse, status_code=201)
async def create_api_key(
    data: APIKeyCreate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create a new API key. The raw key is shown only once."""
    raw_key, key_hash, key_prefix = generate_api_key()
    db_key = APIKey(
        user_id=data.user_id,
        name=data.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=data.scopes,
        expires_at=data.expires_at,
    )
    session.add(db_key)
    await session.flush()
    await session.refresh(db_key)

    response = APIKeyResponse.model_validate(db_key).model_dump()
    response["raw_key"] = raw_key
    return response


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Revoke (deactivate) an API key."""
    db_key = await session.get(APIKey, key_id)
    if db_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    db_key.is_active = False
