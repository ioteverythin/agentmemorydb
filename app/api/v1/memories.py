"""Memory endpoints — upsert, search, stream-search, status, versions, links."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import enforce_tenant, get_current_api_key
from app.db.session import get_session
from app.models.api_key import APIKey
from app.schemas.memory import (
    ContextAssembleRequest,
    ContextAssembleResponse,
    MemoryInvalidateRequest,
    MemoryResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryStatusUpdate,
    MemoryUpsert,
    MemoryVersionResponse,
)
from app.schemas.memory_link import MemoryLinkResponse
from app.schemas.team import ACLGrantRequest, ACLResponse, MemoryShareRequest
from app.services.access_service import AccessService
from app.services.context_assembly_service import ContextAssemblyService
from app.services.memory_service import MemoryService
from app.services.retrieval_service import RetrievalService
from app.services.temporal_service import TemporalService

router = APIRouter()


@router.post("/upsert", response_model=MemoryResponse, status_code=200)
async def upsert_memory(
    data: MemoryUpsert,
    session: AsyncSession = Depends(get_session),
    api_key: APIKey | None = Depends(get_current_api_key),
) -> MemoryResponse:
    """Create or update a canonical memory.

    If an active memory with the same ``memory_key`` already exists for the
    user/scope/project, the previous state is snapshotted and the canonical
    record is updated.
    """
    enforce_tenant(api_key, data.user_id)
    svc = MemoryService(session)
    memory, _is_new = await svc.upsert(data)
    return MemoryResponse.model_validate(memory)


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> MemoryResponse:
    svc = MemoryService(session)
    memory = await svc.get_memory(memory_id)
    return MemoryResponse.model_validate(memory)


@router.post("/search", response_model=MemorySearchResponse)
async def search_memories(
    data: MemorySearchRequest,
    session: AsyncSession = Depends(get_session),
    api_key: APIKey | None = Depends(get_current_api_key),
) -> MemorySearchResponse:
    """Hybrid retrieval endpoint.

    Fuses dense vector similarity and sparse full-text (BM25) rankings via RRF
    when a ``query_text`` is present, applies metadata/layer filtering, and
    re-ranks by composite governance score. Set ``explain=true`` for the
    per-component score breakdown.
    """
    enforce_tenant(api_key, data.user_id)
    svc = RetrievalService(session)
    return await svc.search(data)


@router.post("/assemble-context", response_model=ContextAssembleResponse)
async def assemble_context(
    data: ContextAssembleRequest,
    session: AsyncSession = Depends(get_session),
    api_key: APIKey | None = Depends(get_current_api_key),
) -> ContextAssembleResponse:
    """Assemble retrieved memories into an injection-safe, budget-capped block.

    Retrieves across the memory pyramid, orders stable layers (persona,
    scenario) before volatile ones (atom, raw) for prompt-cache friendliness,
    sanitises each memory against prompt injection, and caps the result by item
    count and character budget so memory never crowds out the task. The
    returned ``context`` string is ready to inject into a system/user prompt.
    """
    enforce_tenant(api_key, data.user_id)
    svc = ContextAssemblyService(session)
    return await svc.assemble(data)


@router.post("/{memory_id}/share", response_model=MemoryResponse)
async def share_memory(
    memory_id: uuid.UUID,
    data: MemoryShareRequest,
    session: AsyncSession = Depends(get_session),
    api_key: APIKey | None = Depends(get_current_api_key),
) -> MemoryResponse:
    """Change a memory's visibility (private / team / restricted / agent).

    Only the memory's owner may share it, and only into a team they belong to.
    """
    enforce_tenant(api_key, data.actor_user_id)
    memory = await AccessService(session).share_memory(
        memory_id=memory_id,
        actor_user_id=data.actor_user_id,
        visibility=data.visibility,
        team_id=data.team_id,
        agent_id=data.agent_id,
    )
    return MemoryResponse.model_validate(memory)


@router.get("/{memory_id}/acl", response_model=list[ACLResponse])
async def list_memory_acl(
    memory_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[ACLResponse]:
    grants = await AccessService(session).list_grants(memory_id)
    return [ACLResponse.model_validate(g) for g in grants]


@router.post("/{memory_id}/acl", response_model=ACLResponse, status_code=201)
async def grant_memory_acl(
    memory_id: uuid.UUID,
    data: ACLGrantRequest,
    session: AsyncSession = Depends(get_session),
    api_key: APIKey | None = Depends(get_current_api_key),
) -> ACLResponse:
    """Grant a user or agent read access to a restricted memory (owner-gated)."""
    enforce_tenant(api_key, data.actor_user_id)
    acl = await AccessService(session).grant(
        memory_id=memory_id,
        actor_user_id=data.actor_user_id,
        principal_type=data.principal_type,
        principal_id=data.principal_id,
    )
    return ACLResponse.model_validate(acl)


@router.delete("/{memory_id}/acl", status_code=200)
async def revoke_memory_acl(
    memory_id: uuid.UUID,
    data: ACLGrantRequest,
    session: AsyncSession = Depends(get_session),
    api_key: APIKey | None = Depends(get_current_api_key),
) -> dict:
    enforce_tenant(api_key, data.actor_user_id)
    revoked = await AccessService(session).revoke(
        memory_id=memory_id,
        actor_user_id=data.actor_user_id,
        principal_type=data.principal_type,
        principal_id=data.principal_id,
    )
    return {"revoked": revoked}


@router.post("/stream-search")
async def stream_search_memories(
    data: MemorySearchRequest,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """SSE streaming search — emits one ``data:`` event per ranked result.

    For large ``top_k`` values or latency-sensitive agents, streaming lets
    consumers start processing the highest-ranked memories before the full
    result set is computed.

    Event format::

        data: {"memory": {...}, "score": {...}}   (one per result)
        ...
        event: done
        data: {"total_candidates": N, "strategy": "hybrid_vector"}
    """
    svc = RetrievalService(session)
    response = await svc.search(data)

    async def _generate():  # type: ignore[return]
        for result in response.results:
            payload = {
                "memory": json.loads(result.memory.model_dump_json()),
                "score": json.loads(result.score.model_dump_json()) if result.score else None,
            }
            yield f"data: {json.dumps(payload)}\n\n"

        done_payload = {
            "total_candidates": response.total_candidates,
            "strategy": response.strategy,
        }
        yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.patch("/{memory_id}/status", response_model=MemoryResponse)
async def update_memory_status(
    memory_id: uuid.UUID,
    data: MemoryStatusUpdate,
    session: AsyncSession = Depends(get_session),
) -> MemoryResponse:
    svc = MemoryService(session)
    memory = await svc.update_status(memory_id, data)
    return MemoryResponse.model_validate(memory)


@router.get("", response_model=list[MemoryResponse])
async def list_memories(
    user_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    memory_type: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    status: str | None = Query(default=None),
    as_of: datetime | None = Query(
        default=None, description="Point-in-time: list the fact generations valid at this instant."
    ),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[MemoryResponse]:
    svc = MemoryService(session)
    memories = await svc.list_memories(
        user_id=user_id,
        project_id=project_id,
        memory_type=memory_type,
        scope=scope,
        status=status,
        limit=limit,
        offset=offset,
        as_of=as_of,
    )
    if as_of is not None:
        return await TemporalService(session).project_as_of(memories, as_of)
    return [MemoryResponse.model_validate(m) for m in memories]


@router.get("/{memory_id}/timeline")
async def get_memory_timeline(
    memory_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """The full supersession chain for a memory, oldest generation first.

    Each generation carries its world-validity window, when the system recorded
    it, and a diff against the previous generation.
    """
    return await TemporalService(session).timeline(memory_id)


@router.post("/{memory_id}/invalidate", response_model=MemoryResponse)
async def invalidate_memory(
    memory_id: uuid.UUID,
    data: MemoryInvalidateRequest,
    session: AsyncSession = Depends(get_session),
    api_key: APIKey | None = Depends(get_current_api_key),
) -> MemoryResponse:
    """Close a fact's validity window with no replacement — it stopped being true.

    The memory remains queryable via ``as_of`` and ``/timeline``, but drops out
    of current-fact retrieval.
    """
    svc = MemoryService(session)
    memory = await svc.get_memory(memory_id)
    enforce_tenant(api_key, memory.user_id)
    memory = await svc.invalidate(memory_id, valid_to=data.valid_to)
    return MemoryResponse.model_validate(memory)


@router.get("/{memory_id}/versions", response_model=list[MemoryVersionResponse])
async def list_memory_versions(
    memory_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[MemoryVersionResponse]:
    svc = MemoryService(session)
    versions = await svc.get_versions(memory_id)
    return [MemoryVersionResponse.model_validate(v) for v in versions]


@router.get("/{memory_id}/links", response_model=list[MemoryLinkResponse])
async def list_memory_links(
    memory_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[MemoryLinkResponse]:
    svc = MemoryService(session)
    links = await svc.get_links(memory_id)
    return [MemoryLinkResponse.model_validate(link) for link in links]
