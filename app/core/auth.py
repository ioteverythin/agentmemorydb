"""API-key authentication middleware and dependency."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.models.api_key import APIKey

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_api_key(raw_key: str) -> str:
    """SHA-256 hash of the raw API key for storage."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns (raw_key, key_hash, key_prefix).
    The raw key is shown once to the user; only the hash is persisted.
    """
    raw_key = f"amdb_{secrets.token_urlsafe(32)}"
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:12]
    return raw_key, key_hash, key_prefix


async def get_current_api_key(
    api_key: str | None = Security(API_KEY_HEADER),
    session: AsyncSession = Depends(get_session),
) -> APIKey | None:
    """Resolve and validate API key from the X-API-Key header.

    Returns None if auth is disabled (development mode).
    Raises 401 if key is missing/invalid when auth is required.
    """
    if not settings.require_auth:
        return None

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide X-API-Key header.",
        )

    key_hash = hash_api_key(api_key)
    stmt = select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active.is_(True))
    result = await session.execute(stmt)
    db_key = result.scalar_one_or_none()

    if db_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key.",
        )

    # Check expiration
    if db_key.expires_at and db_key.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired.",
        )

    # Touch last_used_at
    db_key.last_used_at = datetime.now(timezone.utc)

    return db_key


def require_scope(scope: str):
    """Dependency factory that checks if the API key has a required scope."""

    async def _check(api_key: APIKey | None = Depends(get_current_api_key)) -> APIKey | None:
        if api_key is None:
            return None  # auth disabled
        if api_key.scopes:
            allowed = {s.strip() for s in api_key.scopes.split(",")}
            if "*" not in allowed and scope not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"API key lacks required scope: {scope}",
                )
        return api_key

    return _check
