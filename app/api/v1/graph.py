"""Graph traversal endpoints — expand context via memory links."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.graph_service import GraphTraversalService

router = APIRouter()


class GraphExpandRequest(BaseModel):
    seed_memory_id: uuid.UUID
    max_hops: int = Field(default=2, ge=1, le=5)
    link_types: list[str] | None = None
    max_nodes: int = Field(default=50, ge=1, le=200)
    include_seed: bool = True


class GraphNode(BaseModel):
    memory_id: uuid.UUID
    memory_key: str
    content: str
    depth: int
    link_type: str | None = None
    link_direction: str | None = None


class GraphExpandResponse(BaseModel):
    seed_memory_id: uuid.UUID
    nodes: list[GraphNode]
    total_nodes: int


class ShortestPathRequest(BaseModel):
    source_id: uuid.UUID
    target_id: uuid.UUID
    max_depth: int = Field(default=5, ge=1, le=10)


class ShortestPathResponse(BaseModel):
    source_id: uuid.UUID
    target_id: uuid.UUID
    path: list[uuid.UUID] | None
    path_length: int | None


@router.post("/expand", response_model=GraphExpandResponse)
async def expand_graph(
    data: GraphExpandRequest,
    session: AsyncSession = Depends(get_session),
) -> GraphExpandResponse:
    """Expand context by traversing memory links from a seed memory.

    Uses breadth-first search up to ``max_hops`` depth,
    optionally filtering by link type.
    """
    svc = GraphTraversalService(session)
    nodes = await svc.expand(
        seed_memory_id=data.seed_memory_id,
        max_hops=data.max_hops,
        link_types=data.link_types,
        max_nodes=data.max_nodes,
        include_seed=data.include_seed,
    )
    return GraphExpandResponse(
        seed_memory_id=data.seed_memory_id,
        nodes=[GraphNode(**n) for n in nodes],
        total_nodes=len(nodes),
    )


@router.post("/shortest-path", response_model=ShortestPathResponse)
async def find_shortest_path(
    data: ShortestPathRequest,
    session: AsyncSession = Depends(get_session),
) -> ShortestPathResponse:
    """Find the shortest path between two memories via their links."""
    svc = GraphTraversalService(session)
    path = await svc.find_shortest_path(
        source_id=data.source_id,
        target_id=data.target_id,
        max_depth=data.max_depth,
    )
    return ShortestPathResponse(
        source_id=data.source_id,
        target_id=data.target_id,
        path=path,
        path_length=len(path) - 1 if path else None,
    )
