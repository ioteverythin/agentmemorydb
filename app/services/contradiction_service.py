"""Contradiction detection for the Observation → Memory pipeline.

Without this, a new observation that conflicts with an existing memory simply
coexists with it — the classic "the agent still thinks the client is single"
bug. Here, a conflict is resolved *explicitly*:

- ``SAME_FACT_UPDATED`` → the existing fact is **superseded** (Feature 1), so
  the old value gets a closed validity window instead of lingering.
- ``CONTRADICTS`` with lower confidence than the incumbent → the new memory is
  stored as ``disputed`` and linked to the incumbent with a ``contradicts``
  edge, surfacing the conflict rather than silently picking a winner.
- ``UNRELATED`` → nothing happens.

Two classification strategies sit behind one interface. The default
``heuristic`` is deterministic and needs no API key; ``llm`` asks the configured
provider for a strict JSON verdict and **fails closed** to ``UNRELATED`` on any
error, so an LLM outage can never silently corrupt memory.
"""

from __future__ import annotations

import enum
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.memory import Memory
from app.schemas.memory import MemorySearchRequest
from app.utils.similarity import cosine_similarity

logger = logging.getLogger(__name__)


class Verdict(enum.StrEnum):
    SAME_FACT_UPDATED = "same_fact_updated"
    CONTRADICTS = "contradicts"
    UNRELATED = "unrelated"


@dataclass
class ContradictionDecision:
    """What the pipeline should do about an incoming fact."""

    action: str  # "supersede" | "dispute" | "none"
    verdict: Verdict
    target: Memory | None = None
    similarity: float = 0.0
    reason: str | None = None


# ── Classification strategies ───────────────────────────────────────


@runtime_checkable
class ContradictionClassifier(Protocol):
    """Classifies a candidate pair as same-fact / contradiction / unrelated."""

    async def classify(
        self, *, new_content: str, existing: Memory, similarity: float, same_key: bool
    ) -> tuple[Verdict, str | None]: ...


class HeuristicClassifier:
    """Deterministic, dependency-free classification.

    Same ``memory_key``, or similarity above the configured threshold, with
    different content ⇒ the same fact has been updated. Everything else is
    unrelated. This strategy never reports ``CONTRADICTS`` — distinguishing "an
    update" from "a genuine conflict" needs semantics, so that verdict requires
    the ``llm`` strategy.
    """

    async def classify(
        self, *, new_content: str, existing: Memory, similarity: float, same_key: bool
    ) -> tuple[Verdict, str | None]:
        if existing.content.strip() == new_content.strip():
            return Verdict.UNRELATED, "identical content"
        if same_key:
            return Verdict.SAME_FACT_UPDATED, "same memory_key with different content"
        if similarity >= settings.contradiction_similarity_threshold:
            return (
                Verdict.SAME_FACT_UPDATED,
                f"similarity {similarity:.3f} >= threshold with different content",
            )
        return Verdict.UNRELATED, None


_LLM_SYSTEM = (
    "You compare two statements about the same user and classify their relationship. "
    "Respond with ONLY a compact JSON object and nothing else: "
    '{"verdict": "same_fact_updated" | "contradicts" | "unrelated", "reason": "<short>"}. '
    "Use same_fact_updated when the new statement is an updated value for the same "
    "underlying attribute. Use contradicts when both cannot be true at once and "
    "neither is clearly a newer value. Use unrelated when they concern different things."
)


class LLMClassifier:
    """LLM-backed classification. Fails closed to ``UNRELATED``."""

    def __init__(self, provider=None) -> None:
        self._provider = provider

    def _get_provider(self):
        if self._provider is None:
            from app.utils.llm_provider import get_llm_provider

            self._provider = get_llm_provider()
        return self._provider

    async def classify(
        self, *, new_content: str, existing: Memory, similarity: float, same_key: bool
    ) -> tuple[Verdict, str | None]:
        provider = self._get_provider()
        if not getattr(provider, "available", False):
            logger.debug("LLM classifier unavailable; treating pair as unrelated.")
            return Verdict.UNRELATED, "llm unavailable"

        prompt = (
            f"Existing statement: {existing.content}\n"
            f"New statement: {new_content}\n"
            f"Same attribute key: {same_key}\n"
            f"Embedding similarity: {similarity:.3f}"
        )
        try:
            raw = await provider.complete(prompt, system=_LLM_SYSTEM)
            payload = json.loads(_extract_json(raw))
            verdict = Verdict(str(payload["verdict"]).strip().lower())
            return verdict, payload.get("reason")
        except Exception:
            # Fail CLOSED: never let a bad/absent LLM response mutate memory.
            logger.warning("LLM contradiction classification failed; failing closed", exc_info=True)
            return Verdict.UNRELATED, "llm classification failed"


def _extract_json(raw: str) -> str:
    """Tolerate fenced or prose-wrapped JSON from a chatty model."""
    start, end = raw.find("{"), raw.rfind("}")
    return raw[start : end + 1] if start != -1 and end > start else raw


def get_classifier() -> ContradictionClassifier:
    """Resolve the configured strategy (``heuristic`` by default)."""
    if settings.contradiction_strategy.lower() == "llm":
        return LLMClassifier()
    return HeuristicClassifier()


# ── Service ─────────────────────────────────────────────────────────


class ContradictionService:
    def __init__(self, session: AsyncSession, classifier: ContradictionClassifier | None = None):
        self._session = session
        self._classifier = classifier or get_classifier()

    async def evaluate(
        self,
        *,
        user_id: uuid.UUID,
        memory_key: str,
        content: str,
        confidence: float,
        embedding: list[float] | None = None,
        project_id: uuid.UUID | None = None,
    ) -> ContradictionDecision:
        """Decide what to do about an incoming fact.

        Recalls semantically-similar current memories for the user, classifies
        each against the incoming content, and returns the strongest decision.
        """
        candidates = await self._recall(
            user_id=user_id, content=content, embedding=embedding, project_id=project_id
        )

        best: ContradictionDecision | None = None
        for memory in candidates:
            same_key = memory.memory_key == memory_key
            similarity = cosine_similarity(embedding, memory.embedding)
            if not same_key and similarity < settings.contradiction_similarity_threshold:
                continue

            verdict, reason = await self._classifier.classify(
                new_content=content, existing=memory, similarity=similarity, same_key=same_key
            )
            if verdict is Verdict.UNRELATED:
                continue

            if verdict is Verdict.SAME_FACT_UPDATED or same_key:
                # Same key *is* the same fact slot, so a conflict there is an
                # update by definition. Disputing onto the same key would make
                # the upsert supersede the very incumbent being disputed.
                decision = ContradictionDecision(
                    action="supersede",
                    verdict=Verdict.SAME_FACT_UPDATED,
                    target=memory,
                    similarity=similarity,
                    reason=reason,
                )
            else:  # CONTRADICTS across different keys
                # Only demote the newcomer when the incumbent is more confident;
                # otherwise treat it as an update to the same fact.
                if confidence < memory.confidence:
                    decision = ContradictionDecision(
                        action="dispute",
                        verdict=verdict,
                        target=memory,
                        similarity=similarity,
                        reason=reason,
                    )
                else:
                    decision = ContradictionDecision(
                        action="supersede",
                        verdict=Verdict.SAME_FACT_UPDATED,
                        target=memory,
                        similarity=similarity,
                        reason=(reason or "") + " (newcomer at least as confident)",
                    )

            best = _better(best, decision, memory_key)

        return best or ContradictionDecision(action="none", verdict=Verdict.UNRELATED)

    async def _recall(
        self,
        *,
        user_id: uuid.UUID,
        content: str,
        embedding: list[float] | None,
        project_id: uuid.UUID | None,
    ) -> list[Memory]:
        """Recall current, active candidate memories via the retrieval layer."""
        from app.services.retrieval_service import RetrievalService

        # Reuse retrieval (RRF + filters) for candidate generation, then judge
        # pairs in Python so the heuristic path is backend-independent.
        req = MemorySearchRequest(
            user_id=user_id,
            project_id=project_id,
            query_text=content,
            embedding=embedding,
            top_k=settings.contradiction_candidate_top_k,
        )
        response = await RetrievalService(self._session).search(req)

        # Re-load ORM rows (search returns response schemas, not entities).
        memories: list[Memory] = []
        for result in response.results:
            memory = await self._session.get(Memory, result.memory.id)
            if memory is not None and memory.status == "active":
                memories.append(memory)
        return memories


def _better(
    current: ContradictionDecision | None, candidate: ContradictionDecision, memory_key: str
) -> ContradictionDecision:
    """Prefer a same-key match; otherwise the most similar candidate."""
    if current is None:
        return candidate
    current_same_key = current.target is not None and current.target.memory_key == memory_key
    candidate_same_key = candidate.target is not None and candidate.target.memory_key == memory_key
    if candidate_same_key and not current_same_key:
        return candidate
    if current_same_key and not candidate_same_key:
        return current
    return candidate if candidate.similarity > current.similarity else current
