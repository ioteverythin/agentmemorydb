"""Retrieval service — hybrid search with scoring and audit logging."""

from __future__ import annotations

import uuid

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
        """Execute hybrid search and return scored, auditable results."""

        # ── Resolve embedding ───────────────────────────────────
        embedding = req.embedding
        if embedding is None and req.query_text:
            provider = get_embedding_provider()
            vectors = await provider.embed([req.query_text])
            embedding = vectors[0] if vectors else None

        # ── Database search ─────────────────────────────────────
        raw_results = await self._memory_repo.search(
            user_id=req.user_id,
            project_id=req.project_id,
            embedding=embedding,
            memory_types=req.memory_types,
            scopes=req.scopes,
            status=req.status,
            min_confidence=req.min_confidence,
            min_importance=req.min_importance,
            include_expired=req.include_expired,
            limit=req.top_k * 2,  # over-fetch for re-ranking
        )

        # ── Score & re-rank ─────────────────────────────────────
        scored: list[tuple[Memory, float, dict]] = []
        for memory, vec_sim in raw_results:
            recency = compute_recency_score(memory.updated_at)
            final, breakdown = compute_final_score(
                vector_similarity=vec_sim,
                recency_score=recency,
                importance_score=memory.importance_score,
                authority_level=memory.authority_level,
                confidence=memory.confidence,
            )
            scored.append((memory, final, breakdown))

        # Sort descending by final score
        scored.sort(key=lambda x: x[1], reverse=True)
        scored = scored[: req.top_k]

        # ── Build response ──────────────────────────────────────
        strategy = "hybrid_vector" if embedding is not None else "metadata_only"
        results: list[MemorySearchResult] = []
        log_items: list[RetrievalLogItem] = []

        for rank, (memory, final, breakdown) in enumerate(scored, start=1):
            score_bd = ScoreBreakdown(**breakdown) if req.explain else None
            results.append(
                MemorySearchResult(
                    memory=MemoryResponse.model_validate(memory),
                    score=score_bd,
                )
            )
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
