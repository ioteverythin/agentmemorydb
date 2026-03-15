"""AgentRun repository."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun
from app.repositories.base import BaseRepository


class RunRepository(BaseRepository[AgentRun]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(AgentRun, session)
