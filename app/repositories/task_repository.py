"""Task repository."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.task_state_transition import TaskStateTransition
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Task, session)

    async def create_transition(self, transition: TaskStateTransition) -> TaskStateTransition:
        self._session.add(transition)
        await self._session.flush()
        return transition

    async def list_filtered(
        self,
        *,
        user_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        state: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Task]:
        conditions = []
        if user_id:
            conditions.append(Task.user_id == user_id)
        if project_id:
            conditions.append(Task.project_id == project_id)
        if state:
            conditions.append(Task.state == state)
        stmt = (
            select(Task)
            .where(and_(*conditions) if conditions else True)
            .order_by(Task.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
