"""Memory service — canonical memory upsert, status management, search."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.metrics import record_invalidation, record_supersession, record_upsert
from app.models.memory import Memory
from app.models.memory_link import MemoryLink
from app.models.memory_version import MemoryVersion
from app.repositories.memory_repository import MemoryRepository
from app.schemas.memory import MemoryStatusUpdate, MemoryUpsert
from app.services.lifecycle import emit_lifecycle_event, memory_event_payload
from app.utils.embedding_provider import get_embedding_provider
from app.utils.hashing import compute_content_hash
from app.utils.masking import get_default_engine
from app.ws import MemoryEventTypes

logger = logging.getLogger(__name__)

# Map a target status to the most specific lifecycle event.
_STATUS_EVENT_MAP = {
    "archived": MemoryEventTypes.MEMORY_ARCHIVED,
    "retracted": MemoryEventTypes.MEMORY_RETRACTED,
}


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
        self._session = session
        self._repo = MemoryRepository(session)

    # ── Upsert (core feature) ───────────────────────────────────
    async def upsert(self, data: MemoryUpsert, *, emit: bool = True) -> tuple[Memory, bool]:
        """Create or update a canonical memory.

        Returns (memory, is_new) tuple. When ``emit`` is True (default), a
        ``memory.created`` / ``memory.updated`` lifecycle event is fired to
        webhooks and WebSocket subscribers. Batch callers pass ``emit=False``
        to avoid a per-item webhook fan-out.

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
            # ── Invalidate-only: close the window, no replacement ──
            if data.invalidate_only:
                await self._invalidate(existing, valid_to=data.valid_from or datetime.now(UTC))
                record_upsert("invalidate")
                return existing, False

            # Skip update if content is identical
            if existing.content_hash == content_hash:
                # Touch updated_at only — but an explicit pin still applies, so
                # re-upserting unchanged content can pin it.
                existing.updated_at = datetime.now(UTC)
                existing.recency_score = 1.0
                if data.pinned is not None:
                    existing.pinned = data.pinned
                record_upsert("skip_identical")
                return existing, False

            # ── Supersession ──────────────────────────────────────
            # The new generation becomes valid at ``valid_from`` (agents may
            # backdate). The prior generation's world-validity window closes at
            # exactly that instant, so historical windows tile without gaps.
            new_valid_from = data.valid_from or datetime.now(UTC)
            superseded_version = existing.version

            # Snapshot previous version. In-place versioning means the prior
            # content is preserved as a MemoryVersion row (with its full
            # governance envelope), which is the authoritative record of a
            # contradiction/supersession — no self-referential link needed.
            snapshot = await self._repo.snapshot_version(existing, valid_to=new_valid_from)
            snapshot.status = "superseded"

            # Update canonical row
            existing.content = data.content
            existing.content_hash = content_hash
            existing.embedding = data.embedding
            existing.payload = data.payload
            existing.memory_type = data.memory_type
            existing.layer = data.layer
            existing.source_type = data.source_type
            existing.source_event_id = data.source_event_id
            existing.source_observation_id = data.source_observation_id
            existing.source_run_id = data.source_run_id
            existing.authority_level = data.authority_level
            existing.confidence = data.confidence
            existing.importance_score = data.importance_score
            existing.recency_score = 1.0
            # ``None`` means "leave the pin as it is" — pinning is a deliberate
            # operator decision that a routine content update must not clear.
            if data.pinned is not None:
                existing.pinned = data.pinned
            existing.valid_from = new_valid_from
            existing.valid_to = data.valid_to
            existing.expires_at = data.expires_at
            existing.version += 1
            existing.updated_at = datetime.now(UTC)

            record_upsert("update")
            record_supersession()
            if emit:
                payload = memory_event_payload(existing)
                await emit_lifecycle_event(
                    self._session,
                    event_type=MemoryEventTypes.MEMORY_UPDATED,
                    user_id=existing.user_id,
                    data=payload,
                    project_id=existing.project_id,
                    memory_id=existing.id,
                )
                await emit_lifecycle_event(
                    self._session,
                    event_type=MemoryEventTypes.MEMORY_SUPERSEDED,
                    user_id=existing.user_id,
                    data={
                        **payload,
                        "superseded_version": superseded_version,
                        "valid_from": new_valid_from.isoformat(),
                    },
                    project_id=existing.project_id,
                    memory_id=existing.id,
                )
            return existing, False
        else:
            # Create new memory
            memory = Memory(
                user_id=data.user_id,
                project_id=data.project_id,
                memory_key=data.memory_key,
                memory_type=data.memory_type,
                layer=data.layer,
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
                pinned=bool(data.pinned),
                valid_from=data.valid_from or datetime.now(UTC),
                valid_to=data.valid_to,
                expires_at=data.expires_at,
                version=1,
            )
            memory = await self._repo.create(memory)
            record_upsert("create")
            if emit:
                await emit_lifecycle_event(
                    self._session,
                    event_type=MemoryEventTypes.MEMORY_CREATED,
                    user_id=memory.user_id,
                    data=memory_event_payload(memory),
                    project_id=memory.project_id,
                    memory_id=memory.id,
                )
            return memory, True

    # ── Invalidation (close a validity window, no replacement) ──
    async def _invalidate(self, memory: Memory, *, valid_to: datetime, emit: bool = True) -> Memory:
        """Close ``memory``'s world-validity window without a replacement.

        The fact stopped being true. The final generation is snapshotted with
        the closed window and the canonical row is marked ``stale`` so it drops
        out of current-fact retrieval while remaining queryable as-of.
        """
        await self._repo.snapshot_version(memory, valid_to=valid_to)
        memory.valid_to = valid_to
        memory.status = "stale"
        memory.updated_at = datetime.now(UTC)
        record_invalidation()
        if emit:
            await emit_lifecycle_event(
                self._session,
                event_type=MemoryEventTypes.MEMORY_SUPERSEDED,
                user_id=memory.user_id,
                data={
                    **memory_event_payload(memory),
                    "invalidated": True,
                    "valid_to": valid_to.isoformat(),
                },
                project_id=memory.project_id,
                memory_id=memory.id,
            )
        return memory

    async def invalidate(self, memory_id: uuid.UUID, *, valid_to: datetime | None = None) -> Memory:
        """Public invalidation by id — the fact is no longer true."""
        memory = await self.get_memory(memory_id)
        return await self._invalidate(memory, valid_to=valid_to or datetime.now(UTC))

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
        as_of: datetime | None = None,
    ) -> Sequence[Memory]:
        """List memories with optional filters (``as_of`` = point-in-time)."""
        return await self._repo.list_filtered(
            user_id=user_id,
            project_id=project_id,
            memory_type=memory_type,
            scope=scope,
            status=status,
            limit=limit,
            offset=offset,
            as_of=as_of,
        )

    # ── Status management ───────────────────────────────────────
    async def update_status(
        self, memory_id: uuid.UUID, data: MemoryStatusUpdate, *, emit: bool = True
    ) -> Memory:
        """Change the lifecycle status of a memory, emitting a lifecycle event."""
        memory = await self.get_memory(memory_id)
        memory.status = data.status
        memory.updated_at = datetime.now(UTC)
        if emit:
            event_type = _STATUS_EVENT_MAP.get(data.status, MemoryEventTypes.MEMORY_UPDATED)
            await emit_lifecycle_event(
                self._session,
                event_type=event_type,
                user_id=memory.user_id,
                data=memory_event_payload(memory),
                project_id=memory.project_id,
                memory_id=memory.id,
            )
        return memory

    async def set_pinned(self, memory_id: uuid.UUID, *, pinned: bool) -> Memory:
        """Pin or unpin a memory.

        A pinned memory is exempt from importance decay and retention archival —
        the escape hatch for facts that must never be forgotten regardless of
        how rarely they are recalled.
        """
        memory = await self.get_memory(memory_id)
        memory.pinned = pinned
        memory.updated_at = datetime.now(UTC)
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
