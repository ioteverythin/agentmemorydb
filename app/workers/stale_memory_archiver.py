"""Stale memory archiver — placeholder background job.

This worker scans for memories that have exceeded their validity window
or expiration date and transitions them to `archived` or `stale` status.

In production, this would be run as a scheduled job (e.g., via APScheduler,
Celery beat, or a simple cron invocation).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory


async def archive_stale_memories(session: AsyncSession) -> int:
    """Archive memories past their expiration or validity window.

    Returns the number of memories archived.
    """
    now = datetime.now(timezone.utc)

    stmt = (
        update(Memory)
        .where(
            and_(
                Memory.status == "active",
                (
                    (Memory.expires_at.isnot(None) & (Memory.expires_at <= now))
                    | (Memory.valid_to.isnot(None) & (Memory.valid_to <= now))
                ),
            )
        )
        .values(status="stale", updated_at=now)
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount  # type: ignore[return-value]


async def recompute_recency_scores(session: AsyncSession) -> int:
    """Recompute recency_score for all active memories.

    Uses exponential decay with a 72-hour half-life.
    This is a utility function that can be called periodically.
    """
    import math

    now = datetime.now(timezone.utc)
    half_life_hours = 72.0

    stmt = select(Memory).where(Memory.status == "active")
    result = await session.execute(stmt)
    memories = result.scalars().all()

    count = 0
    for memory in memories:
        updated = memory.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age_hours = max((now - updated).total_seconds() / 3600.0, 0.0)
        new_score = math.exp(-math.log(2) * age_hours / half_life_hours)
        memory.recency_score = round(new_score, 6)
        count += 1

    await session.commit()
    return count
