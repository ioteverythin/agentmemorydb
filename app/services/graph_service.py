"""Memory graph traversal — expand context by following links."""

from __future__ import annotations

import uuid
from collections import deque
from typing import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.models.memory_link import MemoryLink


class GraphTraversalService:
    """Walk the memory-link graph to expand context around a seed memory.

    Supports breadth-first traversal up to N hops, with optional
    link-type filtering and cycle detection.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def expand(
        self,
        seed_memory_id: uuid.UUID,
        *,
        max_hops: int = 2,
        link_types: list[str] | None = None,
        max_nodes: int = 50,
        include_seed: bool = True,
    ) -> list[dict]:
        """BFS traversal from a seed memory, returning connected memories.

        Returns a list of dicts with:
            - memory_id: UUID
            - memory_key: str
            - content: str
            - depth: int (hops from seed)
            - link_type: str (how this node was reached)
            - link_direction: "outgoing" | "incoming"
        """
        visited: set[uuid.UUID] = set()
        results: list[dict] = []

        if include_seed:
            seed = await self._session.get(Memory, seed_memory_id)
            if seed:
                results.append(
                    {
                        "memory_id": seed.id,
                        "memory_key": seed.memory_key,
                        "content": seed.content,
                        "depth": 0,
                        "link_type": None,
                        "link_direction": None,
                    }
                )
            visited.add(seed_memory_id)

        # BFS queue: (memory_id, current_depth)
        queue: deque[tuple[uuid.UUID, int]] = deque()
        queue.append((seed_memory_id, 0))

        while queue and len(results) < max_nodes:
            current_id, depth = queue.popleft()

            if depth >= max_hops:
                continue

            links = await self._get_links(current_id, link_types)

            for link in links:
                # Determine the neighbour
                if link.source_memory_id == current_id:
                    neighbour_id = link.target_memory_id
                    direction = "outgoing"
                else:
                    neighbour_id = link.source_memory_id
                    direction = "incoming"

                if neighbour_id in visited:
                    continue
                visited.add(neighbour_id)

                # Fetch the neighbour memory
                neighbour = await self._session.get(Memory, neighbour_id)
                if neighbour is None or neighbour.status != "active":
                    continue

                results.append(
                    {
                        "memory_id": neighbour.id,
                        "memory_key": neighbour.memory_key,
                        "content": neighbour.content,
                        "depth": depth + 1,
                        "link_type": link.link_type,
                        "link_direction": direction,
                    }
                )

                if len(results) >= max_nodes:
                    break

                queue.append((neighbour_id, depth + 1))

        return results

    async def _get_links(
        self,
        memory_id: uuid.UUID,
        link_types: list[str] | None = None,
    ) -> Sequence[MemoryLink]:
        """Get all links touching a memory, optionally filtered by type."""
        conditions = [
            or_(
                MemoryLink.source_memory_id == memory_id,
                MemoryLink.target_memory_id == memory_id,
            )
        ]
        if link_types:
            conditions.append(MemoryLink.link_type.in_(link_types))

        stmt = select(MemoryLink).where(*conditions)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def find_shortest_path(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        max_depth: int = 5,
    ) -> list[uuid.UUID] | None:
        """BFS shortest path between two memories via links.

        Returns the list of memory IDs in the path, or None if no path exists.
        """
        if source_id == target_id:
            return [source_id]

        visited: set[uuid.UUID] = {source_id}
        queue: deque[tuple[uuid.UUID, list[uuid.UUID]]] = deque()
        queue.append((source_id, [source_id]))

        while queue:
            current_id, path = queue.popleft()

            if len(path) - 1 >= max_depth:
                continue

            links = await self._get_links(current_id)
            for link in links:
                neighbour_id = (
                    link.target_memory_id
                    if link.source_memory_id == current_id
                    else link.source_memory_id
                )

                if neighbour_id == target_id:
                    return path + [target_id]

                if neighbour_id not in visited:
                    visited.add(neighbour_id)
                    queue.append((neighbour_id, path + [neighbour_id]))

        return None
