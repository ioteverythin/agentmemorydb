"""Access tracking service — log memory accesses and auto-boost importance."""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.models.memory_access_log import MemoryAccessLog


class AccessTrackingService:
    """Track memory access patterns and auto-boost importance scores.

    Access frequency is a strong signal of memory value.  This service:
    1. Logs every time a memory is accessed.
    2. Computes access frequency metrics.
    3. Provides auto-boost that adjusts importance_score based on access patterns.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log_access(
        self,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        run_id: uuid.UUID | None = None,
        access_type: str = "retrieval",
    ) -> MemoryAccessLog:
        """Record a memory access event."""
        entry = MemoryAccessLog(
            memory_id=memory_id,
            user_id=user_id,
            run_id=run_id,
            access_type=access_type,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def log_batch_access(
        self,
        memory_ids: list[uuid.UUID],
        user_id: uuid.UUID,
        *,
        run_id: uuid.UUID | None = None,
        access_type: str = "retrieval",
    ) -> int:
        """Log access for multiple memories at once (e.g., search results)."""
        entries = [
            MemoryAccessLog(
                memory_id=mid,
                user_id=user_id,
                run_id=run_id,
                access_type=access_type,
            )
            for mid in memory_ids
        ]
        self._session.add_all(entries)
        await self._session.flush()
        return len(entries)

    async def get_access_count(
        self,
        memory_id: uuid.UUID,
        *,
        since: datetime | None = None,
    ) -> int:
        """Get total access count for a memory, optionally since a timestamp."""
        conditions = [MemoryAccessLog.memory_id == memory_id]
        if since:
            conditions.append(MemoryAccessLog.created_at >= since)

        stmt = select(func.count()).where(and_(*conditions))
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def get_top_accessed(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 20,
        since: datetime | None = None,
    ) -> list[tuple[uuid.UUID, int]]:
        """Get the most-accessed memories for a user.

        Returns (memory_id, access_count) pairs ordered by access count desc.
        """
        conditions = [MemoryAccessLog.user_id == user_id]
        if since:
            conditions.append(MemoryAccessLog.created_at >= since)

        stmt = (
            select(
                MemoryAccessLog.memory_id,
                func.count().label("access_count"),
            )
            .where(and_(*conditions))
            .group_by(MemoryAccessLog.memory_id)
            .order_by(func.count().desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def auto_boost_importance(
        self,
        user_id: uuid.UUID,
        *,
        window_hours: int = 168,  # 7 days
        boost_factor: float = 0.05,
        max_importance: float = 1.0,
    ) -> int:
        """Auto-boost importance_score for frequently accessed memories.

        Algorithm:
        - Count accesses per memory in the time window.
        - Compute a boost based on log(1 + access_count) * boost_factor.
        - Apply boost to importance_score, capped at max_importance.

        Returns the number of memories boosted.
        """
        since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        top_memories = await self.get_top_accessed(user_id, limit=100, since=since)

        boosted = 0
        for memory_id, access_count in top_memories:
            memory = await self._session.get(Memory, memory_id)
            if memory is None or memory.status != "active":
                continue

            boost = math.log1p(access_count) * boost_factor
            new_importance = min(memory.importance_score + boost, max_importance)

            if new_importance > memory.importance_score:
                memory.importance_score = round(new_importance, 4)
                memory.updated_at = datetime.now(timezone.utc)
                boosted += 1

        return boosted

    async def get_access_stats(
        self,
        user_id: uuid.UUID,
        *,
        window_hours: int = 168,
    ) -> dict:
        """Get aggregate access statistics for a user."""
        since = datetime.now(timezone.utc) - timedelta(hours=window_hours)

        # Total accesses
        total_stmt = select(func.count()).where(
            MemoryAccessLog.user_id == user_id,
            MemoryAccessLog.created_at >= since,
        )
        total = (await self._session.execute(total_stmt)).scalar() or 0

        # Unique memories accessed
        unique_stmt = (
            select(func.count(func.distinct(MemoryAccessLog.memory_id)))
            .where(
                MemoryAccessLog.user_id == user_id,
                MemoryAccessLog.created_at >= since,
            )
        )
        unique = (await self._session.execute(unique_stmt)).scalar() or 0

        # By access type
        type_stmt = (
            select(
                MemoryAccessLog.access_type,
                func.count().label("count"),
            )
            .where(
                MemoryAccessLog.user_id == user_id,
                MemoryAccessLog.created_at >= since,
            )
            .group_by(MemoryAccessLog.access_type)
        )
        type_result = await self._session.execute(type_stmt)
        by_type = {row[0]: row[1] for row in type_result.all()}

        return {
            "window_hours": window_hours,
            "total_accesses": total,
            "unique_memories_accessed": unique,
            "by_access_type": by_type,
        }
