"""Memory repository — includes upsert-specific and search queries."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import Float, and_, cast, func, null, or_, select
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
        # Bind project scope precisely: a user-scoped lookup (project_id is None)
        # must not match a project-scoped row, and vice versa.
        if project_id is not None:
            conditions.append(Memory.project_id == project_id)
        else:
            conditions.append(Memory.project_id.is_(None))
        stmt = select(Memory).where(and_(*conditions)).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def snapshot_version(self, memory: Memory) -> MemoryVersion:
        """Create a snapshot of the current memory state before update.

        Captures the full governance + validity envelope so a prior version
        can be faithfully restored (content, scores, authority, validity, and
        the pyramid layer/type).
        """
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
            memory_type=memory.memory_type,
            scope=memory.scope,
            layer=memory.layer,
            authority_level=memory.authority_level,
            valid_from=memory.valid_from,
            valid_to=memory.valid_to,
            expires_at=memory.expires_at,
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

    def _base_conditions(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None,
        memory_types: list[str] | None,
        scopes: list[str] | None,
        layers: list[str] | None,
        status: str,
        min_confidence: float | None,
        min_importance: float | None,
        include_expired: bool,
        access_predicate=None,
    ) -> list:
        # A viewer always sees their own memories; ``access_predicate`` (when
        # supplied by the access layer) ORs in memories shared to them.
        owner_clause = Memory.user_id == user_id
        conditions = [
            owner_clause if access_predicate is None else or_(owner_clause, access_predicate),
            Memory.status == status,
        ]
        if project_id is not None:
            conditions.append(Memory.project_id == project_id)
        if memory_types:
            conditions.append(Memory.memory_type.in_(memory_types))
        if scopes:
            conditions.append(Memory.scope.in_(scopes))
        if layers:
            conditions.append(Memory.layer.in_(layers))
        if min_confidence is not None:
            conditions.append(Memory.confidence >= min_confidence)
        if min_importance is not None:
            conditions.append(Memory.importance_score >= min_importance)

        now = datetime.now(UTC)
        if not include_expired:
            conditions.append((Memory.expires_at.is_(None)) | (Memory.expires_at > now))
            conditions.append((Memory.valid_to.is_(None)) | (Memory.valid_to > now))
        return conditions

    async def _maybe_set_ef_search(self) -> None:
        """Apply the configured HNSW ``ef_search`` for this transaction.

        Higher ``ef_search`` trades latency for recall at query time. Only
        meaningful on PostgreSQL with pgvector's HNSW index; a no-op elsewhere.
        """
        if self._session.bind is None or self._session.bind.dialect.name != "postgresql":
            return
        from sqlalchemy import text

        from app.core.config import settings

        # PostgreSQL's SET does not accept bind parameters, so the value must be
        # inlined. Coerce to int first to keep it injection-safe.
        ef = int(settings.hnsw_ef_search)
        await self._session.execute(text(f"SET LOCAL hnsw.ef_search = {ef}"))

    async def search(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        embedding: list[float] | None = None,
        memory_types: list[str] | None = None,
        scopes: list[str] | None = None,
        layers: list[str] | None = None,
        status: str = "active",
        min_confidence: float | None = None,
        min_importance: float | None = None,
        include_expired: bool = False,
        limit: int = 10,
        access_predicate=None,
    ) -> list[tuple[Memory, float | None]]:
        """Vector / metadata search returning (Memory, vector_similarity|None) pairs."""

        conditions = self._base_conditions(
            user_id=user_id,
            project_id=project_id,
            memory_types=memory_types,
            scopes=scopes,
            layers=layers,
            status=status,
            min_confidence=min_confidence,
            min_importance=min_importance,
            include_expired=include_expired,
            access_predicate=access_predicate,
        )

        is_postgres = (
            self._session.bind is not None and self._session.bind.dialect.name == "postgresql"
        )

        if embedding is not None and is_postgres:
            # Vector similarity search using cosine distance
            # 1 - cosine_distance = cosine_similarity
            await self._maybe_set_ef_search()
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
                select(Memory, cast(null(), Float).label("similarity"))
                .where(and_(*conditions))
                .order_by(Memory.updated_at.desc())
                .limit(limit)
            )

        result = await self._session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def search_fulltext(
        self,
        *,
        user_id: uuid.UUID,
        query_text: str,
        project_id: uuid.UUID | None = None,
        memory_types: list[str] | None = None,
        scopes: list[str] | None = None,
        layers: list[str] | None = None,
        status: str = "active",
        min_confidence: float | None = None,
        min_importance: float | None = None,
        include_expired: bool = False,
        limit: int = 10,
        access_predicate=None,
    ) -> list[tuple[Memory, float]]:
        """Full-text (BM25-style) search over the ``search_vector`` column.

        Uses PostgreSQL's ``ts_rank`` against the tsvector maintained by the
        migration-installed trigger. Returns ``(Memory, ts_rank)`` ordered by
        rank descending. On non-PostgreSQL engines (e.g. the SQLite test DB,
        which has no tsvector), returns an empty list so callers degrade to
        pure vector / metadata search.
        """
        if (
            self._session.bind is None
            or self._session.bind.dialect.name != "postgresql"
            or not query_text.strip()
        ):
            return []

        from sqlalchemy import literal_column, text

        conditions = self._base_conditions(
            user_id=user_id,
            project_id=project_id,
            memory_types=memory_types,
            scopes=scopes,
            layers=layers,
            status=status,
            min_confidence=min_confidence,
            min_importance=min_importance,
            include_expired=include_expired,
            access_predicate=access_predicate,
        )
        # ``search_vector`` is maintained by a DB trigger (migration 002) and is
        # not a mapped column, so reference it by name. ``websearch_to_tsquery``
        # tolerates arbitrary user text (no tsquery syntax errors), which also
        # removes an injection foot-gun.
        search_vector = literal_column("search_vector")
        tsquery = func.websearch_to_tsquery("english", query_text)
        rank = func.ts_rank(search_vector, tsquery).label("rank")
        stmt = (
            select(Memory, rank)
            .where(and_(*conditions))
            .where(search_vector.op("@@")(tsquery))
            .order_by(text("rank DESC"))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [(row[0], float(row[1] or 0.0)) for row in result.all()]

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
