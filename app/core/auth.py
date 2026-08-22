"""API-key authentication middleware and dependency."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

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
    if db_key.expires_at and db_key.expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired.",
        )

    # Touch last_used_at
    db_key.last_used_at = datetime.now(UTC)

    return db_key


def enforce_tenant(api_key: APIKey | None, user_id: uuid.UUID | None) -> None:
    """Ensure an authenticated key may act on behalf of ``user_id``.

    This is the tenant-isolation boundary: a key issued to user A cannot read
    or mutate user B's memories by passing a different ``user_id`` in the
    request. A no-op when auth is disabled (``api_key is None``) or tenant
    isolation is turned off, so it is safe to attach to every route.

    Keys with the ``*`` scope (service/admin keys) may act cross-tenant.
    """
    if api_key is None or not settings.enforce_tenant_isolation:
        return
    if api_key.scopes:
        allowed = {s.strip() for s in api_key.scopes.split(",")}
        if "*" in allowed:
            return
    if user_id is not None and api_key.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key is not authorized for this user_id.",
        )


def assert_scope(api_key: APIKey | None, scope: str, *, allow_unscoped: bool = True) -> None:
    """Assert that ``api_key`` carries ``scope``, raising 403 otherwise.

    A no-op when auth is disabled (``api_key is None``). Use this — rather than
    the :func:`require_scope` dependency — when the requirement depends on the
    request itself, e.g. only the destructive ``mode=erase`` branch of a delete
    needs the ``erase`` scope.

    ``allow_unscoped`` keeps the historical behaviour that a key with *no*
    declared scopes is unrestricted. Irreversible operations pass ``False``: a
    key must name ``erase`` (or ``*``) explicitly to hard-delete data, so
    granting erasure is never an accident of leaving ``scopes`` blank.
    """
    if api_key is None:
        return  # auth disabled
    if not api_key.scopes:
        if allow_unscoped:
            return
    else:
        allowed = {s.strip() for s in api_key.scopes.split(",")}
        if "*" in allowed or scope in allowed:
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"API key lacks required scope: {scope}",
    )


def require_scope(scope: str) -> Callable[..., Awaitable[APIKey | None]]:
    """Dependency factory that checks if the API key has a required scope."""

    async def _check(api_key: APIKey | None = Depends(get_current_api_key)) -> APIKey | None:
        assert_scope(api_key, scope)
        return api_key

    return _check
