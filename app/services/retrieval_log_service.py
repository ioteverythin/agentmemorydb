"""Retrieval log service."""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.retrieval_log import RetrievalLog, RetrievalLogItem
from app.repositories.retrieval_log_repository import RetrievalLogRepository
from app.schemas.retrieval_log import RetrievalLogCreate


class RetrievalLogService:
    """Manages retrieval audit logs."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = RetrievalLogRepository(session)

    async def create_log(self, data: RetrievalLogCreate) -> RetrievalLog:
        """Create a retrieval log with its items."""
        log = RetrievalLog(
            run_id=data.run_id,
            user_id=data.user_id,
            strategy=data.strategy,
            filters_json=data.filters_json,
            query_text=data.query_text,
            top_k=data.top_k,
            total_candidates=data.total_candidates,
        )
        items: list[RetrievalLogItem] = []
        if data.items:
            for item_data in data.items:
                items.append(
                    RetrievalLogItem(
                        memory_id=item_data.memory_id,
                        rank=item_data.rank,
                        final_score=item_data.final_score,
                        vector_score=item_data.vector_score,
                        recency_score=item_data.recency_score,
                        importance_score=item_data.importance_score,
                        authority_score=item_data.authority_score,
                        confidence_score=item_data.confidence_score,
                        selected_for_prompt=item_data.selected_for_prompt,
                    )
                )
        return await self._repo.create_with_items(log, items)

    async def list_by_run(self, run_id: uuid.UUID) -> Sequence[RetrievalLog]:
        """Return all retrieval logs for a given run."""
        return await self._repo.list_by_run(run_id)
