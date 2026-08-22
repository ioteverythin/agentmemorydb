"""Tests for contradiction detection in the Observation → Memory pipeline."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.memory import Memory
from app.models.memory_link import MemoryLink
from app.models.user import User
from app.schemas.memory import MemoryUpsert
from app.schemas.observation import ObservationCreate, ObservationPromoteRequest
from app.services.contradiction_service import (
    ContradictionService,
    HeuristicClassifier,
    LLMClassifier,
    Verdict,
    cosine_similarity,
)
from app.services.memory_service import MemoryService
from app.services.observation_service import ObservationService


async def _user(session) -> uuid.UUID:
    uid = uuid.uuid4()
    session.add(User(id=uid, name="contra-user"))
    await session.flush()
    return uid


async def _memory(session, user_id, key, content, *, confidence=0.7):
    mem, _ = await MemoryService(session).upsert(
        MemoryUpsert(
            user_id=user_id,
            memory_key=key,
            memory_type="semantic",
            content=content,
            confidence=confidence,
        )
    )
    await session.flush()
    return mem


class StubClassifier:
    """Deterministic stand-in for the LLM strategy."""

    def __init__(self, verdict: Verdict, reason: str = "stub") -> None:
        self.verdict = verdict
        self.reason = reason
        self.calls = 0

    async def classify(self, *, new_content, existing, similarity, same_key):
        self.calls += 1
        return self.verdict, self.reason


class FakeLLM:
    """Fake provider returning a canned completion."""

    def __init__(self, raw: str, available: bool = True) -> None:
        self.raw = raw
        self.available = available

    async def complete(self, prompt: str, *, system: str | None = None) -> str:
        return self.raw


@pytest.mark.unit
class TestCosine:
    def test_identical_vectors(self):
        assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_missing_vectors(self):
        assert cosine_similarity(None, [1.0]) == 0.0
        assert cosine_similarity([], []) == 0.0


@pytest.mark.unit
class TestHeuristicClassifier:
    clf = HeuristicClassifier()

    @pytest.mark.asyncio
    async def test_same_key_different_content_is_update(self, unit_session):
        user_id = await _user(unit_session)
        mem = await _memory(unit_session, user_id, "fact:city", "Lives in Mumbai.")
        verdict, reason = await self.clf.classify(
            new_content="Lives in Pune.", existing=mem, similarity=0.1, same_key=True
        )
        assert verdict is Verdict.SAME_FACT_UPDATED
        assert "same memory_key" in reason

    @pytest.mark.asyncio
    async def test_identical_content_is_unrelated(self, unit_session):
        user_id = await _user(unit_session)
        mem = await _memory(unit_session, user_id, "fact:city", "Lives in Mumbai.")
        verdict, _ = await self.clf.classify(
            new_content="Lives in Mumbai.", existing=mem, similarity=1.0, same_key=True
        )
        assert verdict is Verdict.UNRELATED

    @pytest.mark.asyncio
    async def test_high_similarity_different_key_is_update(self, unit_session):
        user_id = await _user(unit_session)
        mem = await _memory(unit_session, user_id, "fact:city", "Lives in Mumbai.")
        verdict, _ = await self.clf.classify(
            new_content="Lives in Pune.", existing=mem, similarity=0.99, same_key=False
        )
        assert verdict is Verdict.SAME_FACT_UPDATED

    @pytest.mark.asyncio
    async def test_low_similarity_is_unrelated(self, unit_session):
        user_id = await _user(unit_session)
        mem = await _memory(unit_session, user_id, "fact:city", "Lives in Mumbai.")
        verdict, _ = await self.clf.classify(
            new_content="Likes tennis.", existing=mem, similarity=0.10, same_key=False
        )
        assert verdict is Verdict.UNRELATED

    @pytest.mark.asyncio
    async def test_heuristic_never_reports_contradicts(self, unit_session):
        """Distinguishing a conflict from an update needs semantics (llm)."""
        user_id = await _user(unit_session)
        mem = await _memory(unit_session, user_id, "k", "A.")
        for sim, same_key in [(0.99, True), (0.99, False), (0.1, False)]:
            verdict, _ = await self.clf.classify(
                new_content="B.", existing=mem, similarity=sim, same_key=same_key
            )
            assert verdict is not Verdict.CONTRADICTS


@pytest.mark.unit
class TestLLMClassifier:
    @pytest.mark.asyncio
    async def test_parses_json_verdict(self, unit_session):
        user_id = await _user(unit_session)
        mem = await _memory(unit_session, user_id, "k", "Client is single.")
        clf = LLMClassifier(provider=FakeLLM('{"verdict": "contradicts", "reason": "marital"}'))
        verdict, reason = await clf.classify(
            new_content="Client is married.", existing=mem, similarity=0.9, same_key=False
        )
        assert verdict is Verdict.CONTRADICTS
        assert reason == "marital"

    @pytest.mark.asyncio
    async def test_tolerates_fenced_json(self, unit_session):
        user_id = await _user(unit_session)
        mem = await _memory(unit_session, user_id, "k", "A.")
        raw = 'Sure!\n```json\n{"verdict": "same_fact_updated", "reason": "r"}\n```'
        clf = LLMClassifier(provider=FakeLLM(raw))
        verdict, _ = await clf.classify(
            new_content="B.", existing=mem, similarity=0.9, same_key=False
        )
        assert verdict is Verdict.SAME_FACT_UPDATED

    @pytest.mark.asyncio
    async def test_fails_closed_on_garbage(self, unit_session):
        """A bad LLM response must never mutate memory."""
        user_id = await _user(unit_session)
        mem = await _memory(unit_session, user_id, "k", "A.")
        clf = LLMClassifier(provider=FakeLLM("I'm not JSON"))
        verdict, reason = await clf.classify(
            new_content="B.", existing=mem, similarity=0.9, same_key=False
        )
        assert verdict is Verdict.UNRELATED
        assert "failed" in reason

    @pytest.mark.asyncio
    async def test_unavailable_provider_is_unrelated(self, unit_session):
        user_id = await _user(unit_session)
        mem = await _memory(unit_session, user_id, "k", "A.")
        clf = LLMClassifier(provider=FakeLLM("{}", available=False))
        verdict, reason = await clf.classify(
            new_content="B.", existing=mem, similarity=0.9, same_key=False
        )
        assert verdict is Verdict.UNRELATED
        assert reason == "llm unavailable"


@pytest.mark.unit
class TestEvaluate:
    @pytest.mark.asyncio
    async def test_same_key_yields_supersede(self, unit_session):
        user_id = await _user(unit_session)
        await _memory(unit_session, user_id, "fact:city", "Lives in Mumbai.")
        svc = ContradictionService(unit_session, classifier=HeuristicClassifier())
        decision = await svc.evaluate(
            user_id=user_id,
            memory_key="fact:city",
            content="Lives in Pune.",
            confidence=0.7,
        )
        assert decision.action == "supersede"
        assert decision.target.memory_key == "fact:city"

    @pytest.mark.asyncio
    async def test_no_candidates_yields_none(self, unit_session):
        user_id = await _user(unit_session)
        svc = ContradictionService(unit_session, classifier=HeuristicClassifier())
        decision = await svc.evaluate(
            user_id=user_id, memory_key="new:key", content="Brand new.", confidence=0.7
        )
        assert decision.action == "none"
        assert decision.verdict is Verdict.UNRELATED

    @pytest.mark.asyncio
    async def test_contradicts_with_lower_confidence_disputes(self, unit_session):
        user_id = await _user(unit_session)
        await _memory(unit_session, user_id, "fact:status", "Client is single.", confidence=0.9)
        svc = ContradictionService(
            unit_session, classifier=StubClassifier(Verdict.CONTRADICTS, "marital conflict")
        )
        prev = settings.contradiction_similarity_threshold
        settings.contradiction_similarity_threshold = -1.0
        try:
            decision = await svc.evaluate(
                user_id=user_id,
                memory_key="fact:marital",  # a *different* slot making an incompatible claim
                content="Client is married.",
                confidence=0.4,  # less confident than the incumbent
            )
        finally:
            settings.contradiction_similarity_threshold = prev
        assert decision.action == "dispute"
        assert decision.verdict is Verdict.CONTRADICTS

    @pytest.mark.asyncio
    async def test_contradicts_with_higher_confidence_supersedes(self, unit_session):
        user_id = await _user(unit_session)
        await _memory(unit_session, user_id, "fact:status", "Client is single.", confidence=0.4)
        svc = ContradictionService(unit_session, classifier=StubClassifier(Verdict.CONTRADICTS))
        prev = settings.contradiction_similarity_threshold
        settings.contradiction_similarity_threshold = -1.0
        try:
            decision = await svc.evaluate(
                user_id=user_id,
                memory_key="fact:marital",
                content="Client is married.",
                confidence=0.95,  # more confident → treat as an update
            )
        finally:
            settings.contradiction_similarity_threshold = prev
        assert decision.action == "supersede"


@pytest.mark.unit
class TestPromotionIntegration:
    async def _observation(self, session, user_id, content, confidence=0.8):
        return await ObservationService(session).create_observation(
            ObservationCreate(
                event_id=uuid.uuid4(),
                run_id=uuid.uuid4(),
                user_id=user_id,
                content=content,
                source_type="user_input",
                confidence=confidence,
            )
        )

    @pytest.mark.asyncio
    async def test_disabled_by_default_leaves_promotion_untouched(self, unit_session):
        user_id = await _user(unit_session)
        await _memory(unit_session, user_id, "fact:city", "Lives in Mumbai.")
        obs = await self._observation(unit_session, user_id, "Lives in Pune.")

        # Flag off (default): a different key just creates a second memory.
        _, memory, created = await ObservationService(unit_session).promote(
            obs.id, ObservationPromoteRequest(memory_key="fact:city2")
        )
        assert created is True
        assert memory.memory_key == "fact:city2"

    @pytest.mark.asyncio
    async def test_supersedes_incumbent_when_enabled(self, unit_session):
        user_id = await _user(unit_session)
        incumbent = await _memory(unit_session, user_id, "fact:city", "Lives in Mumbai.")
        obs = await self._observation(unit_session, user_id, "Lives in Pune.")

        prev = settings.enable_contradiction_detection
        settings.enable_contradiction_detection = True
        try:
            # Promoting under a *different* key still resolves onto the incumbent.
            _, memory, created = await ObservationService(unit_session).promote(
                obs.id, ObservationPromoteRequest(memory_key="fact:city")
            )
        finally:
            settings.enable_contradiction_detection = prev

        assert created is False
        assert memory.id == incumbent.id  # superseded in place
        assert memory.content == "Lives in Pune."
        assert memory.version == 2

    @pytest.mark.asyncio
    async def test_dispute_marks_status_and_links(self, unit_session, monkeypatch):
        user_id = await _user(unit_session)
        incumbent = await _memory(
            unit_session, user_id, "fact:status", "Client is single.", confidence=0.9
        )
        obs = await self._observation(unit_session, user_id, "Client is married.", confidence=0.3)

        # Force the CONTRADICTS verdict (heuristic never emits it).
        import app.services.contradiction_service as cs

        monkeypatch.setattr(cs, "get_classifier", lambda: StubClassifier(Verdict.CONTRADICTS))

        prev = settings.enable_contradiction_detection
        prev_threshold = settings.contradiction_similarity_threshold
        settings.enable_contradiction_detection = True
        # Unit-test embeddings are random, so admit any recalled candidate and
        # let the (stubbed) classifier decide.
        settings.contradiction_similarity_threshold = -1.0
        try:
            _, memory, _ = await ObservationService(unit_session).promote(
                obs.id, ObservationPromoteRequest(memory_key="fact:marital", confidence=0.3)
            )
        finally:
            settings.enable_contradiction_detection = prev
            settings.contradiction_similarity_threshold = prev_threshold
        await unit_session.flush()

        assert memory.status == "disputed"
        links = (
            (
                await unit_session.execute(
                    select(MemoryLink).where(MemoryLink.source_memory_id == memory.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(links) == 1
        assert links[0].link_type == "contradicts"
        assert links[0].target_memory_id == incumbent.id
        # Both memories are retained — the conflict is surfaced, not resolved away.
        assert (await unit_session.get(Memory, incumbent.id)).status == "active"
