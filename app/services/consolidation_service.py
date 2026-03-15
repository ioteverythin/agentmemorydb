"""Memory consolidation service — detect near-duplicates and merge memories."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.models.memory_link import MemoryLink
from app.repositories.memory_repository import MemoryRepository
from app.utils.hashing import compute_content_hash


class ConsolidationService:
    """Detect and merge near-duplicate or related memories.

    Strategies:
    1. **Exact duplicates**: Same content_hash across different keys
    2. **Near-duplicates**: High vector similarity (>threshold)
    3. **Merge**: Combine two memories, keep the higher-authority one,
       archive the other, and create links.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = MemoryRepository(session)

    async def find_exact_duplicates(
        self,
        user_id: uuid.UUID,
        *,
        status: str = "active",
    ) -> list[list[Memory]]:
        """Find groups of memories with identical content_hash.

        Returns a list of groups, where each group has 2+ memories
        with the same content hash.
        """
        # Find content_hashes that appear more than once
        subq = (
            select(Memory.content_hash)
            .where(Memory.user_id == user_id, Memory.status == status)
            .group_by(Memory.content_hash)
            .having(func.count(Memory.id) > 1)
        ).subquery()

        stmt = (
            select(Memory)
            .where(
                Memory.user_id == user_id,
                Memory.status == status,
                Memory.content_hash.in_(select(subq.c.content_hash)),
            )
            .order_by(Memory.content_hash, Memory.created_at)
        )
        result = await self._session.execute(stmt)
        memories = result.scalars().all()

        # Group by content_hash
        groups: dict[str, list[Memory]] = {}
        for mem in memories:
            groups.setdefault(mem.content_hash, []).append(mem)

        return [g for g in groups.values() if len(g) > 1]

    async def find_near_duplicates(
        self,
        user_id: uuid.UUID,
        *,
        similarity_threshold: float = 0.92,
        limit: int = 50,
    ) -> list[tuple[Memory, Memory, float]]:
        """Find pairs of memories with very high vector similarity.

        Returns (memory_a, memory_b, similarity) triples.
        Only works when memories have embeddings (pgvector required).
        """
        pairs: list[tuple[Memory, Memory, float]] = []

        # Get all active memories with embeddings
        stmt = (
            select(Memory)
            .where(
                Memory.user_id == user_id,
                Memory.status == "active",
                Memory.embedding.isnot(None),
            )
            .limit(limit * 2)
        )
        result = await self._session.execute(stmt)
        memories = list(result.scalars().all())

        # Pairwise comparison (for small sets; production should use vector index)
        for i, m_a in enumerate(memories):
            if m_a.embedding is None:
                continue
            for m_b in memories[i + 1 :]:
                if m_b.embedding is None or m_a.id == m_b.id:
                    continue
                # Compute cosine similarity using pgvector's distance op
                sim = self._cosine_similarity(m_a.embedding, m_b.embedding)
                if sim >= similarity_threshold:
                    pairs.append((m_a, m_b, sim))
                    if len(pairs) >= limit:
                        return pairs

        return pairs

    async def merge_memories(
        self,
        keep_id: uuid.UUID,
        archive_id: uuid.UUID,
        *,
        reason: str = "Consolidated as duplicate",
    ) -> Memory:
        """Merge two memories: keep one, archive the other, link them.

        The kept memory inherits the higher authority/importance values.
        The archived memory gets status=archived and a link is created.
        """
        keep = await self._session.get(Memory, keep_id)
        archive = await self._session.get(Memory, archive_id)

        if keep is None or archive is None:
            raise ValueError("Both memory IDs must exist")

        # Snapshot the archived memory
        await self._repo.snapshot_version(archive)

        # Inherit max governance values
        keep.authority_level = max(keep.authority_level, archive.authority_level)
        keep.confidence = max(keep.confidence, archive.confidence)
        keep.importance_score = max(keep.importance_score, archive.importance_score)
        keep.updated_at = datetime.now(timezone.utc)
        keep.recency_score = 1.0

        # Archive the duplicate
        archive.status = "archived"
        archive.updated_at = datetime.now(timezone.utc)

        # Create supersedes link
        link = MemoryLink(
            source_memory_id=keep_id,
            target_memory_id=archive_id,
            link_type="supersedes",
            description=reason,
        )
        self._session.add(link)
        await self._session.flush()

        return keep

    async def auto_consolidate(
        self,
        user_id: uuid.UUID,
    ) -> dict:
        """Run automatic consolidation: find exact duplicates and merge.

        Returns a summary with counts of groups found and memories merged.
        """
        groups = await self.find_exact_duplicates(user_id)
        merged_count = 0

        for group in groups:
            # Keep the one with highest authority, then highest importance
            group.sort(
                key=lambda m: (m.authority_level, m.importance_score),
                reverse=True,
            )
            keeper = group[0]
            for dup in group[1:]:
                await self.merge_memories(keeper.id, dup.id)
                merged_count += 1

        return {
            "duplicate_groups_found": len(groups),
            "memories_merged": merged_count,
        }

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        import math

        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
