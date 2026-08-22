"""Temporal service — point-in-time projection and supersession timelines.

EngramDB is **bitemporal** (see ``docs/temporal-model.md``):

- *World time* — ``valid_from`` / ``valid_to`` on a memory: when the fact was
  true in the world. ``valid_to IS NULL`` marks the current generation.
- *System time* — ``created_at`` plus the ``memory_versions`` chain: when the
  system came to believe it.

The canonical ``memories`` row always holds the **current** generation and keeps
a stable id (so links, ACL grants, and client-held ids stay valid). Prior
generations live in ``memory_versions`` with closed windows that tile the past.
This service resolves "what did we believe at time T?" against that chain.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.models.memory_version import MemoryVersion
from app.schemas.memory import MemoryResponse


def _aware(ts: datetime | None) -> datetime | None:
    """Coerce a possibly-naive timestamp (SQLite round-trips naive) to UTC."""
    if ts is None:
        return None
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts


def _window_contains(valid_from: datetime | None, valid_to: datetime | None, at: datetime) -> bool:
    """True when ``at`` falls in ``[valid_from, valid_to)``."""
    start = _aware(valid_from)
    end = _aware(valid_to)
    if start is not None and start > at:
        return False
    return end is None or end > at


class TemporalService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def project_as_of(
        self, memories: Sequence[Memory], as_of: datetime
    ) -> list[MemoryResponse]:
        """Project memories to the generation that was valid at ``as_of``.

        Retrieval finds the *fact slot* (a ``memory_key``) using the current
        row's embedding; this step resolves *which value* that slot held at
        ``as_of``. Rows whose current generation was already valid then pass
        through unchanged; rows superseded since are replaced by the matching
        historical version. A memory with no generation valid at ``as_of``
        (created later, or invalidated before) is dropped.
        """
        at = _aware(as_of) or as_of
        projected: list[MemoryResponse] = []

        for memory in memories:
            if _window_contains(memory.valid_from, memory.valid_to, at):
                projected.append(MemoryResponse.model_validate(memory))
                continue

            version = await self._version_at(memory.id, at)
            if version is None:
                continue  # nothing was valid at that instant — omit entirely
            projected.append(self._as_response(memory, version))

        return projected

    async def _version_at(self, memory_id: uuid.UUID, at: datetime) -> MemoryVersion | None:
        """The historical generation whose validity window contains ``at``."""
        rows = (
            (
                await self._session.execute(
                    select(MemoryVersion)
                    .where(MemoryVersion.memory_id == memory_id)
                    .order_by(MemoryVersion.version.desc())
                )
            )
            .scalars()
            .all()
        )
        for v in rows:
            if _window_contains(v.valid_from, v.valid_to, at):
                return v
        return None

    @staticmethod
    def _as_response(memory: Memory, version: MemoryVersion) -> MemoryResponse:
        """Overlay a historical version onto its canonical memory's identity."""
        base = MemoryResponse.model_validate(memory)
        return base.model_copy(
            update={
                "content": version.content,
                "content_hash": version.content_hash,
                "payload": version.payload,
                "confidence": version.confidence,
                "importance_score": version.importance_score,
                "source_type": version.source_type,
                "status": version.status,
                "memory_type": version.memory_type or memory.memory_type,
                "layer": version.layer or memory.layer,
                "authority_level": (
                    version.authority_level
                    if version.authority_level is not None
                    else memory.authority_level
                ),
                "valid_from": version.valid_from,
                "valid_to": version.valid_to,
                "version": version.version,
            }
        )

    # ── Timeline ────────────────────────────────────────────────
    async def timeline(self, memory_id: uuid.UUID) -> dict:
        """The full supersession chain for a memory, oldest generation first.

        Each hop carries its validity window and a diff against the previous
        generation, so a caller can answer "what changed, and when did we start
        believing it?" without reconstructing state client-side.
        """
        memory = await self._session.get(Memory, memory_id)
        if memory is None:
            from app.core.errors import NotFoundError

            raise NotFoundError("Memory", memory_id)

        versions = (
            (
                await self._session.execute(
                    select(MemoryVersion)
                    .where(MemoryVersion.memory_id == memory_id)
                    .order_by(MemoryVersion.version.asc())
                )
            )
            .scalars()
            .all()
        )

        generations: list[dict] = []
        previous_content: str | None = None
        for v in versions:
            generations.append(
                {
                    "version": v.version,
                    "content": v.content,
                    "valid_from": v.valid_from,
                    "valid_to": v.valid_to,
                    "status": v.status,
                    "is_current": False,
                    "recorded_at": v.superseded_at,
                    "diff": _diff(previous_content, v.content),
                }
            )
            previous_content = v.content

        # The canonical row is the current (open) generation.
        generations.append(
            {
                "version": memory.version,
                "content": memory.content,
                "valid_from": memory.valid_from,
                "valid_to": memory.valid_to,
                "status": memory.status,
                "is_current": memory.valid_to is None,
                "recorded_at": memory.updated_at,
                "diff": _diff(previous_content, memory.content),
            }
        )

        return {
            "memory_id": str(memory.id),
            "memory_key": memory.memory_key,
            "user_id": str(memory.user_id),
            "generation_count": len(generations),
            "superseded_by": str(memory.superseded_by) if memory.superseded_by else None,
            "generations": generations,
        }


def _diff(before: str | None, after: str) -> dict:
    """A compact, dependency-free diff between two generations of content."""
    if before is None:
        return {"kind": "created", "added": after, "removed": None}
    if before == after:
        return {"kind": "unchanged", "added": None, "removed": None}
    before_words = set(before.split())
    after_words = set(after.split())
    return {
        "kind": "revised",
        "added": " ".join(w for w in after.split() if w not in before_words) or None,
        "removed": " ".join(w for w in before.split() if w not in after_words) or None,
    }
