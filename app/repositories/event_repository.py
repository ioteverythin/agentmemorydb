"""Event repository."""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.repositories.base import BaseRepository


class EventRepository(BaseRepository[Event]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Event, session)

    async def list_by_run(self, run_id: uuid.UUID) -> Sequence[Event]:
        stmt = (
            select(Event)
            .where(Event.run_id == run_id)
            .order_by(Event.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
