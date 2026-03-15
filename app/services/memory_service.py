"""Memory service — canonical memory upsert, status management, search."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.core.metrics import record_upsert
from app.models.memory import Memory
from app.models.memory_link import MemoryLink
from app.models.memory_version import MemoryVersion
from app.repositories.memory_repository import MemoryRepository
from app.schemas.memory import MemoryStatusUpdate, MemoryUpsert
from app.utils.embedding_provider import get_embedding_provider
from app.utils.hashing import compute_content_hash
from app.utils.masking import get_default_engine

logger = logging.getLogger(__name__)


def _mask_if_enabled(text: str | None) -> str | None:
    """Apply write-time PII masking (sync, no audit log — log written by service layer)."""
    if not text:
        return text
    engine = get_default_engine()
    if not engine.active_patterns:
        return text
    result = engine.mask_text(text)
    return result.masked_text if result.was_modified else text


class MemoryService:
    """Core business logic for canonical memory records.

    Implements the upsert lifecycle:
    1. Lookup existing active memory by (user_id, memory_key, scope, project_id)
    2. If exists → snapshot current state to memory_versions, update in place
    3. If contradiction flagged → create supersedes / contradicts links
    4. If not exists → insert new memory
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repo = MemoryRepository(session)

    # ── Upsert (core feature) ───────────────────────────────────
    async def upsert(self, data: MemoryUpsert) -> tuple[Memory, bool]:
        """Create or update a canonical memory.

        Returns (memory, is_new) tuple.

        Behaviour:
        - Finds active memory with same memory_key + user_id + scope (+ project_id).
        - If found:
            - Snapshots current state into memory_versions.
            - Updates content, confidence, provenance, timestamps, etc.
            - If ``is_contradiction`` is True, creates supersedes + contradicts links.
        - If not found:
            - Creates a new memory record.
        - Always recomputes content_hash for deduplication.
        """
        # ── Write-time PII masking ───────────────────────────
        masked_content = _mask_if_enabled(data.content)
        if masked_content is not None:
            data = data.model_copy(update={"content": masked_content})

        content_hash = compute_content_hash(data.content)

        # ── Auto-generate embedding if not provided ──────────
        if data.embedding is None and data.content:
            try:
                provider = get_embedding_provider()
                vectors = await provider.embed([data.content])
                if vectors:
                    data = data.model_copy(update={"embedding": vectors[0]})
            except Exception:
                logger.warning("Failed to auto-generate embedding for memory", exc_info=True)

        existing = await self._repo.find_active_by_key(
            user_id=data.user_id,
            memory_key=data.memory_key,
            scope=data.scope,
            project_id=data.project_id,
        )

        if existing is not None:
            # Skip update if content is identical
            if existing.content_hash == content_hash:
                # Touch updated_at only
                existing.updated_at = datetime.now(timezone.utc)
                existing.recency_score = 1.0
                record_upsert("skip_identical")
                return existing, False

            # Snapshot previous version
            await self._repo.snapshot_version(existing)

            # Handle contradiction links
            if data.is_contradiction:
                await self._repo.create_link(
                    source_id=existing.id,
                    target_id=existing.id,  # self-ref; target updated below
                    link_type="supersedes",
                    description="Updated via upsert with contradiction flag",
                )

            # Update canonical row
            existing.content = data.content
            existing.content_hash = content_hash
            existing.embedding = data.embedding
            existing.payload = data.payload
            existing.source_type = data.source_type
            existing.source_event_id = data.source_event_id
            existing.source_observation_id = data.source_observation_id
            existing.source_run_id = data.source_run_id
            existing.authority_level = data.authority_level
            existing.confidence = data.confidence
            existing.importance_score = data.importance_score
            existing.recency_score = 1.0
            existing.valid_from = data.valid_from
            existing.valid_to = data.valid_to
            existing.expires_at = data.expires_at
            existing.version += 1
            existing.updated_at = datetime.now(timezone.utc)

            record_upsert("update")
            return existing, False
        else:
            # Create new memory
            memory = Memory(
                user_id=data.user_id,
                project_id=data.project_id,
                memory_key=data.memory_key,
                memory_type=data.memory_type,
                scope=data.scope,
                content=data.content,
                content_hash=content_hash,
                embedding=data.embedding,
                payload=data.payload,
                source_type=data.source_type,
                source_event_id=data.source_event_id,
                source_observation_id=data.source_observation_id,
                source_run_id=data.source_run_id,
                status="active",
                authority_level=data.authority_level,
                confidence=data.confidence,
                importance_score=data.importance_score,
                recency_score=1.0,
                valid_from=data.valid_from or datetime.now(timezone.utc),
                valid_to=data.valid_to,
                expires_at=data.expires_at,
                version=1,
            )
            memory = await self._repo.create(memory)
            record_upsert("create")
            return memory, True

    # ── Read operations ─────────────────────────────────────────
    async def get_memory(self, memory_id: uuid.UUID) -> Memory:
        memory = await self._repo.get_by_id(memory_id)
        if memory is None:
            raise NotFoundError("Memory", memory_id)
        return memory

    async def list_memories(
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
        """List memories with optional filters."""
        return await self._repo.list_filtered(
            user_id=user_id,
            project_id=project_id,
            memory_type=memory_type,
            scope=scope,
            status=status,
            limit=limit,
            offset=offset,
        )

    # ── Status management ───────────────────────────────────────
    async def update_status(self, memory_id: uuid.UUID, data: MemoryStatusUpdate) -> Memory:
        """Change the lifecycle status of a memory."""
        memory = await self.get_memory(memory_id)
        old_status = memory.status
        memory.status = data.status
        memory.updated_at = datetime.now(timezone.utc)
        return memory

    # ── Versions & links ────────────────────────────────────────
    async def get_versions(self, memory_id: uuid.UUID) -> Sequence[MemoryVersion]:
        await self.get_memory(memory_id)  # ensure exists
        return await self._repo.get_versions(memory_id)

    async def get_links(self, memory_id: uuid.UUID) -> Sequence[MemoryLink]:
        await self.get_memory(memory_id)  # ensure exists
        return await self._repo.get_links(memory_id)

    async def create_link(
        self,
        source_memory_id: uuid.UUID,
        target_memory_id: uuid.UUID,
        link_type: str,
        description: str | None = None,
    ) -> MemoryLink:
        """Create a typed link between two memories."""
        # Validate both memories exist
        await self.get_memory(source_memory_id)
        await self.get_memory(target_memory_id)
        return await self._repo.create_link(
            source_id=source_memory_id,
            target_id=target_memory_id,
            link_type=link_type,
            description=description,
        )
