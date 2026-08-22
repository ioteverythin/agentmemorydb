"""Automatic memory linking — building the graph without being asked.

EngramDB already has a typed memory graph: ``supersedes`` from bitemporal
supersession, ``contradicts`` from conflict resolution, ``derived_from`` from
reflection. All three are written by processes that *know* the relationship
because they created it. Nothing writes the plain "these two are about the same
thing" edge, so in practice the graph stays sparse — traversal and
``/graph/expand`` only reach memories somebody explicitly linked, which is
almost none of them.

Autolinking fills that in. When a memory is written, the most similar existing
memories get a ``related_to`` edge. The result is that graph expansion from any
memory reaches its topical neighbourhood, without an agent ever having to
reason about which links to create.

Three constraints keep this from degrading into noise:

1. **A high bar and a low cap.** Only links above
   ``AUTOLINK_SIMILARITY_THRESHOLD``, and at most ``AUTOLINK_MAX_LINKS`` per
   write. A generous threshold would connect everything to everything, which is
   the same as connecting nothing.
2. **Undirected deduplication.** ``related_to`` is symmetric, so A→B and B→A are
   the same edge. Only one is stored, and a re-write never adds a second.
3. **Nothing untrustworthy is linked.** Quarantined and disputed memories are
   neither sources nor targets: an edge from a trusted memory to a poisoned one
   is a path an agent can traverse, which would route around the very quarantine
   that held it back.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.metrics import record_autolink
from app.models.memory import Memory
from app.models.memory_link import MemoryLink
from app.utils.similarity import cosine_similarity

logger = logging.getLogger(__name__)

LINK_TYPE = "related_to"

# Statuses that may not take part in an automatic link, in either direction.
_UNLINKABLE = frozenset({"quarantined", "disputed", "retracted"})


class AutolinkService:
    """Creates ``related_to`` edges between topically similar memories."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _candidates(self, memory: Memory) -> Sequence[Memory]:
        """Other active memories of the same owner, capped for scanning.

        Restricted to the memory's own project scope so an autolink never
        silently bridges two projects that were deliberately kept apart.
        """
        conds = [
            Memory.user_id == memory.user_id,
            Memory.id != memory.id,
            Memory.status == "active",
            Memory.embedding.is_not(None),
        ]
        if memory.project_id is not None:
            conds.append(Memory.project_id == memory.project_id)
        else:
            conds.append(Memory.project_id.is_(None))

        rows = await self._session.execute(
            select(Memory)
            .where(and_(*conds))
            .order_by(Memory.updated_at.desc())
            .limit(settings.autolink_candidate_pool)
        )
        return rows.scalars().all()

    async def _existing_edges(self, memory_id: uuid.UUID) -> set[uuid.UUID]:
        """Every memory already linked to this one, in either direction.

        ``related_to`` is symmetric, so an existing B→A edge must suppress a new
        A→B: otherwise every re-write of either memory adds another copy of the
        same relationship.
        """
        rows = await self._session.execute(
            select(MemoryLink.source_memory_id, MemoryLink.target_memory_id).where(
                MemoryLink.link_type == LINK_TYPE,
                or_(
                    MemoryLink.source_memory_id == memory_id,
                    MemoryLink.target_memory_id == memory_id,
                ),
            )
        )
        linked: set[uuid.UUID] = set()
        for source_id, target_id in rows.all():
            linked.add(target_id if source_id == memory_id else source_id)
        return linked

    async def autolink(self, memory: Memory) -> list[MemoryLink]:
        """Link ``memory`` to its nearest neighbours. A no-op unless enabled.

        Returns the links created (possibly none). Never raises: a failure to
        enrich the graph must not fail the write that triggered it.
        """
        if not settings.enable_autolink:
            return []
        if memory.embedding is None or memory.status in _UNLINKABLE:
            return []

        try:
            return await self._autolink(memory)
        except Exception:  # pragma: no cover - defensive
            logger.warning("Autolink failed for memory %s", memory.id, exc_info=True)
            return []

    async def autolink_now(self, memory: Memory) -> list[MemoryLink]:
        """Link a memory on explicit request, regardless of the feature flag.

        The flag governs *automatic* linking on write. Someone calling the
        endpoint has already decided; refusing them because a background
        behaviour is switched off would be obtuse. Errors propagate here — an
        explicit request should report its failure rather than swallow it.
        """
        if memory.embedding is None or memory.status in _UNLINKABLE:
            return []
        return await self._autolink(memory)

    async def _autolink(self, memory: Memory) -> list[MemoryLink]:
        candidates = await self._candidates(memory)
        if not candidates:
            return []

        already_linked = await self._existing_edges(memory.id)
        vector = list(memory.embedding)

        scored: list[tuple[float, Memory]] = []
        for candidate in candidates:
            if candidate.id in already_linked or candidate.status in _UNLINKABLE:
                continue
            score = cosine_similarity(vector, list(candidate.embedding))
            if score >= settings.autolink_similarity_threshold:
                scored.append((score, candidate))

        scored.sort(key=lambda pair: pair[0], reverse=True)

        created: list[MemoryLink] = []
        for score, candidate in scored[: settings.autolink_max_links]:
            link = MemoryLink(
                source_memory_id=memory.id,
                target_memory_id=candidate.id,
                link_type=LINK_TYPE,
                description=f"autolinked (similarity {score:.3f})",
            )
            self._session.add(link)
            created.append(link)

        if created:
            await self._session.flush()
            record_autolink(len(created))
        return created

    async def backfill(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 500,
        dry_run: bool = False,
    ) -> dict:
        """Autolink a user's existing memories.

        Turning the flag on only affects new writes, which leaves an established
        store exactly as sparse as it was. This walks what is already there.
        Safe to re-run: dedup means a second pass adds nothing.
        """
        rows = await self._session.execute(
            select(Memory)
            .where(
                Memory.user_id == user_id,
                Memory.status == "active",
                Memory.embedding.is_not(None),
            )
            .order_by(Memory.updated_at.desc())
            .limit(limit)
        )
        memories = list(rows.scalars().all())

        links_created = 0
        for memory in memories:
            if dry_run:
                # Count what *would* be linked without writing anything.
                already = await self._existing_edges(memory.id)
                vector = list(memory.embedding)
                matches = 0
                for candidate in await self._candidates(memory):
                    if candidate.id in already or candidate.status in _UNLINKABLE:
                        continue
                    if (
                        cosine_similarity(vector, list(candidate.embedding))
                        >= settings.autolink_similarity_threshold
                    ):
                        matches += 1
                links_created += min(matches, settings.autolink_max_links)
            else:
                links_created += len(await self._autolink(memory))

        return {
            "memories_scanned": len(memories),
            "links_created": links_created,
            "dry_run": dry_run,
        }
