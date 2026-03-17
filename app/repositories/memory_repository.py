"""Memory repository — includes upsert-specific and search queries."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.models.memory_link import MemoryLink
from app.models.memory_version import MemoryVersion
from app.repositories.base import BaseRepository


class MemoryRepository(BaseRepository[Memory]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Memory, session)

    async def find_active_by_key(
        self,
        user_id: uuid.UUID,
        memory_key: str,
        scope: str = "user",
        project_id: uuid.UUID | None = None,
    ) -> Memory | None:
        """Find the active canonical memory for a given key in scope."""
        conditions = [
            Memory.user_id == user_id,
            Memory.memory_key == memory_key,
            Memory.scope == scope,
            Memory.status == "active",
        ]
        if project_id is not None:
            conditions.append(Memory.project_id == project_id)
        stmt = select(Memory).where(and_(*conditions)).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def snapshot_version(self, memory: Memory) -> MemoryVersion:
        """Create a snapshot of the current memory state before update."""
        version = MemoryVersion(
            memory_id=memory.id,
            version=memory.version,
            content=memory.content,
            content_hash=memory.content_hash,
            payload=memory.payload,
            confidence=memory.confidence,
            importance_score=memory.importance_score,
            source_type=memory.source_type,
            status=memory.status,
            created_at=memory.created_at,
            superseded_at=datetime.now(UTC),
        )
        self._session.add(version)
        await self._session.flush()
        return version

    async def create_link(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        link_type: str,
        description: str | None = None,
    ) -> MemoryLink:
        link = MemoryLink(
            source_memory_id=source_id,
            target_memory_id=target_id,
            link_type=link_type,
            description=description,
        )
        self._session.add(link)
        await self._session.flush()
        return link

    async def get_versions(self, memory_id: uuid.UUID) -> Sequence[MemoryVersion]:
        stmt = (
            select(MemoryVersion)
            .where(MemoryVersion.memory_id == memory_id)
            .order_by(MemoryVersion.version.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_links(self, memory_id: uuid.UUID) -> Sequence[MemoryLink]:
        stmt = select(MemoryLink).where(
            (MemoryLink.source_memory_id == memory_id) | (MemoryLink.target_memory_id == memory_id)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def search(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        embedding: list[float] | None = None,
        memory_types: list[str] | None = None,
        scopes: list[str] | None = None,
        status: str = "active",
        min_confidence: float | None = None,
        min_importance: float | None = None,
        include_expired: bool = False,
        limit: int = 10,
    ) -> list[tuple[Memory, float | None]]:
        """Hybrid search returning (Memory, vector_similarity|None) pairs."""

        conditions = [
            Memory.user_id == user_id,
            Memory.status == status,
        ]

        if project_id is not None:
            conditions.append(Memory.project_id == project_id)
        if memory_types:
            conditions.append(Memory.memory_type.in_(memory_types))
        if scopes:
            conditions.append(Memory.scope.in_(scopes))
        if min_confidence is not None:
            conditions.append(Memory.confidence >= min_confidence)
        if min_importance is not None:
            conditions.append(Memory.importance_score >= min_importance)

        now = datetime.now(UTC)
        if not include_expired:
            conditions.append((Memory.expires_at.is_(None)) | (Memory.expires_at > now))
            conditions.append((Memory.valid_to.is_(None)) | (Memory.valid_to > now))

        if embedding is not None:
            # Vector similarity search using cosine distance
            # 1 - cosine_distance = cosine_similarity
            "[" + ",".join(str(x) for x in embedding) + "]"
            cosine_dist = Memory.embedding.cosine_distance(embedding)
            similarity = (1 - cosine_dist).label("similarity")
            stmt = (
                select(Memory, similarity)
                .where(and_(*conditions))
                .where(Memory.embedding.isnot(None))
                .order_by(cosine_dist.asc())
                .limit(limit)
            )
        else:
            # Metadata-only fallback — order by recency
            stmt = (
                select(Memory, text("NULL::float AS similarity"))
                .where(and_(*conditions))
                .order_by(Memory.updated_at.desc())
                .limit(limit)
            )

        result = await self._session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def list_filtered(
        self,
        *,
        user_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        memory_type: str | None = None,
        scope: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Memory]:
        conditions = []
        if user_id:
            conditions.append(Memory.user_id == user_id)
        if project_id:
            conditions.append(Memory.project_id == project_id)
        if memory_type:
            conditions.append(Memory.memory_type == memory_type)
        if scope:
            conditions.append(Memory.scope == scope)
        if status:
            conditions.append(Memory.status == status)
        stmt = select(Memory).where(and_(*conditions)).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return result.scalars().all()
