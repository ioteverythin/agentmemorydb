"""Integration tests for RRF hybrid retrieval (vector + full-text) and
injection-safe context assembly against real PostgreSQL + pgvector.

Requires DATABASE_URL pointing at a pgvector-enabled Postgres with the
migration-installed ``search_vector`` tsvector trigger.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.user import User
from app.schemas.memory import ContextAssembleRequest, MemorySearchRequest, MemoryUpsert
from app.services.context_assembly_service import ContextAssemblyService
from app.services.memory_service import MemoryService
from app.services.retrieval_service import RetrievalService

pytestmark = pytest.mark.integration


async def _user(session) -> uuid.UUID:
    uid = uuid.uuid4()
    session.add(User(id=uid, name="rrf-user"))
    await session.flush()
    return uid


async def _store(svc, uid, key, content, *, layer="atom"):
    await svc.upsert(
        MemoryUpsert(
            user_id=uid,
            memory_key=key,
            memory_type="semantic",
            layer=layer,
            content=content,
        )
    )


@pytest.mark.asyncio
async def test_strategy_is_hybrid_rrf_with_query(integration_session):
    uid = await _user(integration_session)
    svc = MemoryService(integration_session)
    await _store(svc, uid, "k1", "The deployment runbook lives in the ops wiki.")
    await _store(svc, uid, "k2", "The user prefers Python over Go for scripting.")
    await integration_session.flush()

    retr = RetrievalService(integration_session)
    resp = await retr.search(
        MemorySearchRequest(user_id=uid, query_text="deployment runbook", top_k=5, explain=True)
    )
    # Full-text + vector both ran → RRF fusion.
    assert resp.strategy == "hybrid_rrf"
    assert resp.results, "expected at least one result"


@pytest.mark.asyncio
async def test_fulltext_finds_lexical_match(integration_session):
    """A rare exact term is surfaced by BM25/FTS.

    Tests are seeded with *random* dummy embeddings, so the fused ranking's
    vector component is noise — we therefore assert on the deterministic FTS
    path directly (it ranks the exact lexical match first), and separately that
    the fused search attaches an rrf_score to that memory. Using top_k that
    covers all rows keeps the second assertion independent of the random vector
    ordering.
    """
    uid = await _user(integration_session)
    svc = MemoryService(integration_session)
    await _store(svc, uid, "target", "The incident postmortem referenced kubernetes zalgo-token.")
    for i in range(8):
        await _store(svc, uid, f"noise{i}", f"Some unrelated note number {i} about coffee.")
    await integration_session.flush()

    # 1. Full-text search alone ranks the exact lexical match first (deterministic).
    from app.repositories.memory_repository import MemoryRepository

    fts = await MemoryRepository(integration_session).search_fulltext(
        user_id=uid, query_text="zalgo-token", limit=5
    )
    assert fts, "FTS should match the rare term"
    assert fts[0][0].memory_key == "target"

    # 2. In the fused (RRF) search the match carries an rrf_score. top_k covers
    #    every row so presence doesn't depend on the random vector ranking.
    resp = await RetrievalService(integration_session).search(
        MemorySearchRequest(user_id=uid, query_text="zalgo-token", top_k=20, explain=True)
    )
    assert resp.strategy == "hybrid_rrf"
    target = next(r for r in resp.results if r.memory.memory_key == "target")
    assert target.score is not None and target.score.rrf_score is not None


@pytest.mark.asyncio
async def test_use_fulltext_false_falls_back_to_vector(integration_session):
    uid = await _user(integration_session)
    svc = MemoryService(integration_session)
    await _store(svc, uid, "k1", "vector-only path check")
    await integration_session.flush()

    retr = RetrievalService(integration_session)
    resp = await retr.search(
        MemorySearchRequest(
            user_id=uid, query_text="vector", top_k=5, use_fulltext=False, explain=True
        )
    )
    assert resp.strategy == "hybrid_vector"


@pytest.mark.asyncio
async def test_layer_filter(integration_session):
    uid = await _user(integration_session)
    svc = MemoryService(integration_session)
    await _store(svc, uid, "p1", "persona level cognition", layer="persona")
    await _store(svc, uid, "a1", "atomic level fact", layer="atom")
    await integration_session.flush()

    retr = RetrievalService(integration_session)
    resp = await retr.search(
        MemorySearchRequest(user_id=uid, query_text="level", layers=["persona"], top_k=5)
    )
    assert {r.memory.layer for r in resp.results} == {"persona"}


@pytest.mark.asyncio
async def test_context_assembly_end_to_end(integration_session):
    uid = await _user(integration_session)
    svc = MemoryService(integration_session)
    await _store(
        svc, uid, "persona1", "The user is a staff engineer who values brevity.", layer="persona"
    )
    await _store(svc, uid, "atom1", "The auth service owner is team-identity.", layer="atom")
    await integration_session.flush()

    asm = ContextAssemblyService(integration_session)
    resp = await asm.assemble(
        ContextAssembleRequest(user_id=uid, query_text="auth owner", top_k=10)
    )
    assert resp.included_count >= 1
    assert "<memory-context>" in resp.context
    assert resp.token_estimate == len(resp.context) // 4
