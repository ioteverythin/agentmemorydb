"""RetrievalLog repository."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.retrieval_log import RetrievalLog, RetrievalLogItem
from app.repositories.base import BaseRepository


class RetrievalLogRepository(BaseRepository[RetrievalLog]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(RetrievalLog, session)

    async def create_with_items(
        self, log: RetrievalLog, items: list[RetrievalLogItem]
    ) -> RetrievalLog:
        self._session.add(log)
        await self._session.flush()
        for item in items:
            item.retrieval_log_id = log.id
            self._session.add(item)
        await self._session.flush()
        await self._session.refresh(log)
        return log

    async def list_by_run(self, run_id: uuid.UUID) -> Sequence[RetrievalLog]:
        stmt = (
            select(RetrievalLog)
            .options(selectinload(RetrievalLog.items))
            .where(RetrievalLog.run_id == run_id)
            .order_by(RetrievalLog.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
