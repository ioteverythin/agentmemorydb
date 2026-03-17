"""Observation repository."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.observation import Observation
from app.repositories.base import BaseRepository


class ObservationRepository(BaseRepository[Observation]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Observation, session)

    async def list_by_event(self, event_id: uuid.UUID) -> Sequence[Observation]:
        stmt = (
            select(Observation)
            .where(Observation.event_id == event_id)
            .order_by(Observation.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
