"""Feedback service — adjust memory importance based on explicit agent signals.

Inspired by MemRL's RL reward signal: agents can explicitly rate whether a
retrieved memory was useful (+1) or not (-1).  Unlike the passive
access-frequency boost, this reflects *utility*, not just popularity.

Algorithm
---------
Each feedback vote shifts ``importance_score`` by ``FEEDBACK_STEP``,
clamped to [0, 1].  Positive feedback (+1) increases importance;
negative feedback (-1) decreases it.  The direction is always applied;
magnitude is configurable via ``FEEDBACK_STEP`` (default 0.05).

This is a deliberate simplification.  A future upgrade could:
- Weight recent votes more than old ones (exponential forgiveness).
- Batch votes and apply a moving average.
- Use votes as a reward signal to train a lightweight retrieval policy.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.models.memory_access_log import MemoryAccessLog


class FeedbackService:
    """Apply explicit utility feedback to memory importance scores."""

    FEEDBACK_STEP: float = 0.05  # how much each vote shifts importance

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_feedback(
        self,
        *,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
        vote: int,  # +1 (useful) or -1 (not useful)
        run_id: uuid.UUID | None = None,
        context: str | None = None,
    ) -> dict:
        """Record a feedback vote and adjust the memory's importance score.

        Parameters
        ----------
        memory_id:
            The memory that was retrieved and rated.
        user_id:
            The user (or agent identity) submitting the feedback.
        vote:
            ``+1`` — memory was useful; ``-1`` — memory was not useful.
        run_id:
            Optional agent run the feedback comes from.
        context:
            Optional free-text note explaining the rating.

        Returns
        -------
        dict with ``memory_id``, old/new ``importance_score``, and ``vote``.
        """
        if vote not in (1, -1):
            raise ValueError("vote must be +1 or -1")

        # Load memory
        result = await self._session.execute(select(Memory).where(Memory.id == memory_id))
        memory = result.scalar_one_or_none()
        if memory is None:
            raise LookupError(f"Memory {memory_id} not found")

        old_score = memory.importance_score
        delta = self.FEEDBACK_STEP * vote
        new_score = max(0.0, min(1.0, old_score + delta))
        memory.importance_score = new_score
        memory.updated_at = datetime.now(UTC)
        self._session.add(memory)

        # Log as a special access_type so it's queryable
        log = MemoryAccessLog(
            memory_id=memory_id,
            user_id=user_id,
            run_id=run_id,
            access_type="feedback_positive" if vote > 0 else "feedback_negative",
        )
        self._session.add(log)
        await self._session.flush()

        return {
            "memory_id": str(memory_id),
            "vote": vote,
            "importance_score_before": round(old_score, 4),
            "importance_score_after": round(new_score, 4),
            "context": context,
        }
