"""Retrieval service — hybrid search with scoring and audit logging."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.metrics import record_search
from app.models.memory import Memory
from app.models.retrieval_log import RetrievalLog, RetrievalLogItem
from app.repositories.memory_repository import MemoryRepository
from app.repositories.retrieval_log_repository import RetrievalLogRepository
from app.schemas.memory import (
    MemoryResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemorySearchResult,
    ScoreBreakdown,
)
from app.services.access_tracking_service import AccessTrackingService
from app.utils.embedding_provider import get_embedding_provider
from app.utils.rrf import reciprocal_rank_fusion
from app.utils.scoring import compute_final_score, compute_recency_score


class RetrievalService:
    """Hybrid memory retrieval with scoring and audit trail.

    Search strategy:
    1. Apply metadata filters (user, scope, status, types, validity).
    2. If embedding provided → vector similarity search.
    3. Compute composite score per result:
       final = 0.45 * vector_sim + 0.20 * recency + 0.15 * importance
               + 0.10 * authority_norm + 0.10 * confidence
    4. Re-rank by final score.
    5. Log the retrieval request + items to retrieval_logs/retrieval_log_items.
    6. Return scored results with optional score breakdown.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._memory_repo = MemoryRepository(session)
        self._log_repo = RetrievalLogRepository(session)
        self._access_tracker = AccessTrackingService(session)

    async def search(self, req: MemorySearchRequest) -> MemorySearchResponse:
        """Execute hybrid search and return scored, auditable results.

        When a ``query_text`` is present and the backend supports full-text
        search, dense (vector) and sparse (BM25/FTS) candidate rankings are
        combined with Reciprocal Rank Fusion, then re-ranked by the composite
        governance score (recency, importance, authority, confidence). This
        surfaces both semantically-similar and lexically-exact matches, and
        lets high-authority/recent memories outside the top vector neighbours
        still win.
        """

        # ── Resolve embedding ───────────────────────────────────
        embedding = req.embedding
        if embedding is None and req.query_text:
            provider = get_embedding_provider()
            vectors = await provider.embed([req.query_text])
            embedding = vectors[0] if vectors else None

        overfetch = max(req.top_k * settings.retrieval_overfetch_multiplier, req.top_k)

        # ── Viewer access predicate (opt-in team/shared retrieval) ─
        access_predicate = None
        if req.include_shared:
            from app.services.access_service import AccessService
            from app.services.team_service import TeamService

            team_ids = await TeamService(self._session).get_user_team_ids(req.user_id)
            access_predicate = AccessService(self._session).accessible_predicate(
                viewer_user_id=req.user_id,
                team_ids=team_ids,
                as_agent_id=req.as_agent_id,
            )

        # ── Dense (vector / metadata) candidates ────────────────
        vector_results = await self._memory_repo.search(
            user_id=req.user_id,
            project_id=req.project_id,
            embedding=embedding,
            memory_types=req.memory_types,
            scopes=req.scopes,
            layers=req.layers,
            status=req.status,
            min_confidence=req.min_confidence,
            min_importance=req.min_importance,
            include_expired=req.include_expired,
            limit=overfetch,
            access_predicate=access_predicate,
            as_of=req.as_of,
        )

        # ── Sparse (full-text / BM25) candidates ────────────────
        fts_results: list[tuple[Memory, float]] = []
        if req.use_fulltext and req.query_text and settings.enable_fulltext_search:
            fts_results = await self._memory_repo.search_fulltext(
                user_id=req.user_id,
                query_text=req.query_text,
                project_id=req.project_id,
                memory_types=req.memory_types,
                scopes=req.scopes,
                layers=req.layers,
                status=req.status,
                min_confidence=req.min_confidence,
                min_importance=req.min_importance,
                include_expired=req.include_expired,
                limit=overfetch,
                access_predicate=access_predicate,
                as_of=req.as_of,
            )

        # ── Merge candidate pools ───────────────────────────────
        memory_by_id: dict = {}
        sim_by_id: dict = {}
        for memory, vec_sim in vector_results:
            memory_by_id[memory.id] = memory
            sim_by_id[memory.id] = vec_sim
        for memory, _rank in fts_results:
            memory_by_id.setdefault(memory.id, memory)
            sim_by_id.setdefault(memory.id, None)

        # ── Reciprocal Rank Fusion (only when both signals exist) ─
        rrf_scores: dict = {}
        used_rrf = bool(fts_results)
        if used_rrf:
            vec_ids = [m.id for m, _ in vector_results]
            fts_ids = [m.id for m, _ in fts_results]
            rrf_scores = reciprocal_rank_fusion([vec_ids, fts_ids], k=settings.rrf_k)
        max_rrf = max(rrf_scores.values()) if rrf_scores else 0.0

        # ── Composite score & re-rank ───────────────────────────
        w_ft = settings.fulltext_weight
        scored: list[tuple[Memory, float, dict]] = []
        for mem_id, memory in memory_by_id.items():
            vec_sim = sim_by_id.get(mem_id)
            recency = compute_recency_score(memory.updated_at)
            final, breakdown = compute_final_score(
                vector_similarity=vec_sim,
                recency_score=recency,
                importance_score=memory.importance_score,
                authority_level=memory.authority_level,
                confidence=memory.confidence,
            )
            sort_score = final
            if used_rrf:
                rrf_norm = (rrf_scores.get(mem_id, 0.0) / max_rrf) if max_rrf > 0 else 0.0
                breakdown["rrf_score"] = round(rrf_scores.get(mem_id, 0.0), 6)
                # Blend: composite governance score plus a full-text nudge.
                sort_score = (1.0 - w_ft) * final + w_ft * rrf_norm
            scored.append((memory, sort_score, breakdown))

        # Sort descending by (blended) score
        scored.sort(key=lambda x: x[1], reverse=True)
        scored = scored[: req.top_k]

        raw_results = list(memory_by_id.values())

        # ── Build response ──────────────────────────────────────
        if used_rrf:
            strategy = "hybrid_rrf"
        elif embedding is not None:
            strategy = "hybrid_vector"
        else:
            strategy = "metadata_only"
        results: list[MemorySearchResult] = []
        log_items: list[RetrievalLogItem] = []

        # ── Point-in-time projection ────────────────────────────
        # Ranking finds the *fact slot*; if as_of predates a row's current
        # generation, substitute the generation that was valid then. A memory
        # with no generation valid at as_of is dropped from the results.
        projected_by_id: dict = {}
        if req.as_of is not None:
            from app.services.temporal_service import TemporalService

            temporal = TemporalService(self._session)
            for view in await temporal.project_as_of([m for m, _, _ in scored], req.as_of):
                projected_by_id[view.id] = view

        for rank, (memory, final, breakdown) in enumerate(scored, start=1):
            if req.as_of is not None:
                view = projected_by_id.get(memory.id)
                if view is None:
                    continue
            else:
                view = MemoryResponse.model_validate(memory)
            score_bd = ScoreBreakdown(**breakdown) if req.explain else None
            results.append(MemorySearchResult(memory=view, score=score_bd))
            log_items.append(
                RetrievalLogItem(
                    memory_id=memory.id,
                    rank=rank,
                    final_score=final,
                    vector_score=breakdown.get("vector_score"),
                    recency_score=breakdown["recency_score"],
                    importance_score=breakdown["importance_score"],
                    authority_score=breakdown["authority_score"],
                    confidence_score=breakdown["confidence_score"],
                    selected_for_prompt=True,
                )
            )

        # ── Audit log ───────────────────────────────────────────
        log = RetrievalLog(
            run_id=req.run_id,
            user_id=req.user_id,
            strategy=strategy,
            filters_json={
                "memory_types": req.memory_types,
                "scopes": req.scopes,
                "status": req.status,
                "min_confidence": req.min_confidence,
                "min_importance": req.min_importance,
                "include_expired": req.include_expired,
            },
            query_text=req.query_text,
            top_k=req.top_k,
            total_candidates=len(raw_results),
        )
        await self._log_repo.create_with_items(log, log_items)

        # ── Metrics ─────────────────────────────────────────────
        record_search(strategy)

        # ── Access tracking ─────────────────────────────────────
        if settings.enable_access_tracking and scored:
            await self._access_tracker.log_batch_access(
                memory_ids=[m.id for m, _, _ in scored],
                user_id=req.user_id,
                run_id=req.run_id,
                access_type="retrieval",
            )

        return MemorySearchResponse(
            results=results,
            total_candidates=len(raw_results),
            strategy=strategy,
        )
