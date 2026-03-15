"""Health and version endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.config import settings
from app.db.session import get_session

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    return {"status": "ok", "service": settings.app_name}


@router.get("/health/deep")
async def deep_health_check(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Deep health check — verifies database connectivity and pgvector."""
    checks: dict = {"service": settings.app_name, "status": "ok"}

    # Database connectivity
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
        checks["status"] = "degraded"

    # pgvector availability
    try:
        await session.execute(text("SELECT 'test'::vector(3)"))
        checks["pgvector"] = "ok"
    except Exception:
        checks["pgvector"] = "unavailable"
        checks["status"] = "degraded"

    # Memory count (quick gauge)
    try:
        result = await session.execute(
            text("SELECT count(*) FROM memories WHERE status = 'active'")
        )
        checks["active_memories"] = result.scalar() or 0
    except Exception:
        checks["active_memories"] = "unavailable"

    return checks


@router.get("/version")
async def version() -> dict:
    return {
        "version": __version__,
        "service": settings.app_name,
        "auth_required": settings.require_auth,
        "embedding_provider": settings.embedding_provider,
        "features": {
            "webhooks": settings.enable_webhooks,
            "metrics": settings.enable_metrics,
            "fulltext_search": settings.enable_fulltext_search,
            "access_tracking": settings.enable_access_tracking,
        },
    }
