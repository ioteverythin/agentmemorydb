"""Artifact repository."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact import ArtifactMetadata
from app.repositories.base import BaseRepository


class ArtifactRepository(BaseRepository[ArtifactMetadata]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ArtifactMetadata, session)
