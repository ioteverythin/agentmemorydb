"""Forgetting — importance/access-aware archival.

Replaces the blunt ``importance < 0.3`` archive rule with a retention score
that blends recency, importance, and how often a memory is actually used. A
rarely-flagged-important but frequently-recalled fact survives; a stale,
low-value, never-recalled one decays. Distilled layers (persona, scenario) are
exempt by default — they are deliberate roll-ups, not raw churn.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.memory import Memory
from app.models.memory_access_log import MemoryAccessLog
from app.utils.scoring import compute_recency_score, compute_retention_score


def _aware(ts: datetime | None) -> datetime | None:
    """Coerce a possibly-naive timestamp (SQLite round-trips naive) to UTC."""
    if ts is None:
        return None
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts


def _max_ts(a: datetime, b: datetime | None) -> datetime:
    a_ = _aware(a)
    b_ = _aware(b)
    if b_ is None:
        return a_
    return a_ if a_ >= b_ else b_


class ForgettingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _exempt_layers(self) -> set[str]:
        return {s.strip() for s in settings.forgetting_exempt_layers.split(",") if s.strip()}

    async def archive_low_retention(self, *, dry_run: bool = False) -> dict:
        """Archive active memories whose retention score falls below threshold.

        A single grouped query pulls each eligible memory with its lifetime
        access count, retention is computed in Python, and the losers are
        archived in one UPDATE — no per-row round-trips.
        """
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=settings.forgetting_min_age_days)
        exempt = self._exempt_layers()

        # Eligible = active, older than min age, not a distilled layer.
        conds = [Memory.status == "active", Memory.updated_at < cutoff]
        if exempt:
            conds.append(Memory.layer.notin_(exempt))

        stmt = (
            select(
                Memory.id,
                Memory.updated_at,
                Memory.importance_score,
                func.count(MemoryAccessLog.id).label("access_count"),
                func.max(MemoryAccessLog.created_at).label("last_access"),
            )
            .outerjoin(MemoryAccessLog, MemoryAccessLog.memory_id == Memory.id)
            .where(*conds)
            .group_by(Memory.id, Memory.updated_at, Memory.importance_score)
        )
        rows = (await self._session.execute(stmt)).all()

        threshold = settings.forgetting_retention_threshold
        to_archive: list = []
        for mem_id, updated_at, importance, access_count, last_access in rows:
            # Recency tracks last *activity* — a write or a recall — so a
            # frequently-recalled memory reads as recently active and is kept.
            last_active = _max_ts(updated_at, last_access)
            retention = compute_retention_score(
                recency_score=compute_recency_score(last_active, now),
                importance_score=importance,
                access_count=int(access_count or 0),
                weight_recency=settings.forget_weight_recency,
                weight_importance=settings.forget_weight_importance,
                weight_access=settings.forget_weight_access,
                access_saturation=settings.forgetting_access_saturation,
            )
            if retention < threshold:
                to_archive.append(mem_id)

        if to_archive and not dry_run:
            await self._session.execute(
                update(Memory)
                .where(Memory.id.in_(to_archive))
                .values(status="archived", updated_at=now)
            )

        return {
            "candidates": len(rows),
            "archived": len(to_archive),
            "threshold": threshold,
            "dry_run": dry_run,
        }
