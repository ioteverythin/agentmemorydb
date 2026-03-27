"""Tests for the three research-paper–inspired add-on features.

Feature 1 — MemRL Feedback Loop:
    TestFeedbackSchema (2 tests)
    TestFeedbackService (5 tests)
    TestFeedbackEndpoint (3 tests)

Feature 2 — EverMemOS Auto User Profiling:
    TestUserProfileService (5 tests)
    TestProfilingSettings (2 tests)
    TestProfilingSchedulerJob (2 tests)

Feature 3 — MAGMA Entity Tagging:
    TestEntityExtractor (9 tests)
    TestEntityMerge (3 tests)
    TestEntityExtractionInUpsert (3 tests)

Total: 34 tests
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

# =====================================================================
# Feature 1 — MemRL Feedback Loop
# =====================================================================


@pytest.mark.unit
class TestFeedbackSchema:
    """Validate FeedbackRequest schema constraints."""

    def test_valid_positive_vote(self):
        from app.schemas.memory import FeedbackRequest

        req = FeedbackRequest(user_id=uuid.uuid4(), vote=1)
        assert req.vote == 1

    def test_valid_negative_vote(self):
        from app.schemas.memory import FeedbackRequest

        req = FeedbackRequest(user_id=uuid.uuid4(), vote=-1)
        assert req.vote == -1

    def test_invalid_vote_rejected(self):
        from pydantic import ValidationError

        from app.schemas.memory import FeedbackRequest

        with pytest.raises(ValidationError):
            FeedbackRequest(user_id=uuid.uuid4(), vote=2)

    def test_optional_fields_default_none(self):
        from app.schemas.memory import FeedbackRequest

        req = FeedbackRequest(user_id=uuid.uuid4(), vote=1)
        assert req.run_id is None
        assert req.context is None

    def test_context_max_length(self):
        from pydantic import ValidationError

        from app.schemas.memory import FeedbackRequest

        with pytest.raises(ValidationError):
            FeedbackRequest(user_id=uuid.uuid4(), vote=1, context="x" * 513)


@pytest.mark.unit
class TestFeedbackService:
    """Unit tests for FeedbackService business logic."""

    def _make_memory(self, importance: float = 0.5) -> MagicMock:
        m = MagicMock()
        m.id = uuid.uuid4()
        m.importance_score = importance
        m.user_id = uuid.uuid4()
        return m

    @pytest.mark.asyncio
    async def test_positive_vote_increases_score(self):
        from app.services.feedback_service import FeedbackService

        session = AsyncMock()
        memory = self._make_memory(0.5)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = memory
        session.execute = AsyncMock(return_value=mock_result)
        session.add = MagicMock()
        session.flush = AsyncMock()

        svc = FeedbackService(session)
        result = await svc.record_feedback(
            memory_id=memory.id,
            user_id=memory.user_id,
            vote=1,
        )

        assert result["importance_score_after"] == pytest.approx(0.55)
        assert result["vote"] == 1

    @pytest.mark.asyncio
    async def test_negative_vote_decreases_score(self):
        from app.services.feedback_service import FeedbackService

        session = AsyncMock()
        memory = self._make_memory(0.5)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = memory
        session.execute = AsyncMock(return_value=mock_result)
        session.add = MagicMock()
        session.flush = AsyncMock()

        svc = FeedbackService(session)
        result = await svc.record_feedback(
            memory_id=memory.id,
            user_id=memory.user_id,
            vote=-1,
        )

        assert result["importance_score_after"] == pytest.approx(0.45)

    @pytest.mark.asyncio
    async def test_score_clamped_at_1(self):
        from app.services.feedback_service import FeedbackService

        session = AsyncMock()
        memory = self._make_memory(0.98)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = memory
        session.execute = AsyncMock(return_value=mock_result)
        session.add = MagicMock()
        session.flush = AsyncMock()

        svc = FeedbackService(session)
        result = await svc.record_feedback(
            memory_id=memory.id,
            user_id=memory.user_id,
            vote=1,
        )

        assert result["importance_score_after"] <= 1.0

    @pytest.mark.asyncio
    async def test_score_clamped_at_0(self):
        from app.services.feedback_service import FeedbackService

        session = AsyncMock()
        memory = self._make_memory(0.02)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = memory
        session.execute = AsyncMock(return_value=mock_result)
        session.add = MagicMock()
        session.flush = AsyncMock()

        svc = FeedbackService(session)
        result = await svc.record_feedback(
            memory_id=memory.id,
            user_id=memory.user_id,
            vote=-1,
        )

        assert result["importance_score_after"] >= 0.0

    @pytest.mark.asyncio
    async def test_missing_memory_raises_lookup_error(self):
        from app.services.feedback_service import FeedbackService

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        svc = FeedbackService(session)
        with pytest.raises(LookupError):
            await svc.record_feedback(
                memory_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                vote=1,
            )


@pytest.mark.unit
class TestFeedbackEndpoint:
    """Tests for POST /memories/{id}/feedback route structure."""

    def test_feedback_request_schema_in_memory_module(self):
        """FeedbackRequest must be importable from schemas.memory."""
        from app.schemas.memory import FeedbackRequest

        assert FeedbackRequest is not None

    def test_feedback_service_importable(self):
        from app.services.feedback_service import FeedbackService

        assert FeedbackService is not None

    def test_feedback_service_has_record_feedback_method(self):
        from app.services.feedback_service import FeedbackService

        assert callable(FeedbackService.record_feedback)


# =====================================================================
# Feature 2 — EverMemOS Auto User Profiling
# =====================================================================


@pytest.mark.unit
class TestUserProfileService:
    """Unit tests for UserProfileService.synthesize()."""

    def _make_memory(self, mtype: str = "episodic", content: str = "some content") -> MagicMock:
        m = MagicMock()
        m.id = uuid.uuid4()
        m.memory_type = mtype
        m.content = content
        m.importance_score = 0.5
        m.updated_at = datetime.now(UTC)
        return m

    @pytest.mark.asyncio
    async def test_skips_when_no_memories(self):
        from unittest.mock import AsyncMock, MagicMock

        from app.services.user_profile_service import UserProfileService

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        svc = UserProfileService(session)
        result = await svc.synthesize(uuid.uuid4())

        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_creates_profile_when_memories_exist(self):
        from unittest.mock import AsyncMock, MagicMock

        from app.services.user_profile_service import UserProfileService

        memories = [self._make_memory("episodic", f"did task {i}") for i in range(3)]
        session = AsyncMock()

        # First execute = fetch top memories
        mock_top = MagicMock()
        mock_top.scalars.return_value.all.return_value = memories

        # Second execute = find existing profile (None)
        mock_existing = MagicMock()
        mock_existing.scalar_one_or_none.return_value = None

        session.execute = AsyncMock(side_effect=[mock_top, mock_existing])
        session.add = MagicMock()
        session.flush = AsyncMock()

        svc = UserProfileService(session)
        result = await svc.synthesize(uuid.uuid4())

        assert result["status"] == "ok"
        assert result["action"] == "created"
        assert result["input_memories"] == 3

    @pytest.mark.asyncio
    async def test_updates_existing_profile(self):
        from unittest.mock import AsyncMock, MagicMock

        from app.services.user_profile_service import UserProfileService

        memories = [self._make_memory()]
        existing_profile = MagicMock()
        existing_profile.content = "old profile"

        session = AsyncMock()
        mock_top = MagicMock()
        mock_top.scalars.return_value.all.return_value = memories
        mock_existing = MagicMock()
        mock_existing.scalar_one_or_none.return_value = existing_profile
        session.execute = AsyncMock(side_effect=[mock_top, mock_existing])
        session.add = MagicMock()
        session.flush = AsyncMock()

        svc = UserProfileService(session)
        result = await svc.synthesize(uuid.uuid4())

        assert result["action"] == "updated"

    def test_plain_summary_contains_type_headers(self):
        from app.services.user_profile_service import UserProfileService

        svc = UserProfileService(MagicMock())
        by_type = {"episodic": ["went to store", "called alice"], "semantic": ["knows Python"]}
        summary = svc._plain_summary(by_type)

        assert "[EPISODIC]" in summary
        assert "[SEMANTIC]" in summary
        assert "went to store" in summary

    def test_profile_key_constant(self):
        from app.services.user_profile_service import PROFILE_KEY

        assert PROFILE_KEY == "__profile__"


@pytest.mark.unit
class TestProfilingSettings:
    """Verify EverMemOS profiling settings exist with correct defaults."""

    def test_profile_interval_default(self):
        from app.core.config import settings

        assert settings.scheduler_profile_interval == 240

    def test_profiling_enabled_by_default(self):
        from app.core.config import settings

        assert settings.scheduler_enable_profiling is True


@pytest.mark.unit
class TestProfilingSchedulerJob:
    """Verify the synthesize_user_profiles job is registered in the scheduler."""

    def test_job_registered(self):
        from app.workers.scheduler import MaintenanceScheduler

        sched = MaintenanceScheduler()
        job_names = [j.name for j in sched._jobs]
        assert "synthesize_user_profiles" in job_names

    def test_job_uses_profile_interval(self):
        from app.core.config import settings
        from app.workers.scheduler import MaintenanceScheduler

        sched = MaintenanceScheduler()
        job = next(j for j in sched._jobs if j.name == "synthesize_user_profiles")
        assert job.interval_minutes == settings.scheduler_profile_interval


# =====================================================================
# Feature 3 — MAGMA Entity Tagging
# =====================================================================


@pytest.mark.unit
class TestEntityExtractor:
    """Unit tests for the regex-based entity extractor."""

    def test_extracts_email(self):
        from app.utils.entity_extractor import extract_entities

        result = extract_entities("Contact alice@example.com for details.")
        assert "alice@example.com" in result["emails"]

    def test_extracts_url(self):
        from app.utils.entity_extractor import extract_entities

        result = extract_entities("See https://api.example.com/v1/docs for API docs.")
        assert any("api.example.com" in u for u in result["urls"])

    def test_extracts_mention(self):
        from app.utils.entity_extractor import extract_entities

        result = extract_entities("Ping @alice and @bob_smith for review.")
        assert "@alice" in result["mentions"]
        assert "@bob_smith" in result["mentions"]

    def test_extracts_iso_date(self):
        from app.utils.entity_extractor import extract_entities

        result = extract_entities("The meeting is on 2024-03-15 at noon.")
        assert "2024-03-15" in result["dates"]

    def test_extracts_number_with_unit(self):
        from app.utils.entity_extractor import extract_entities

        result = extract_entities("Latency is 42 ms and size is 3.5 GB.")
        assert any("42" in n for n in result["numbers"])
        assert any("3.5" in n for n in result["numbers"])

    def test_extracts_proper_noun_phrases(self):
        from app.utils.entity_extractor import extract_entities

        result = extract_entities("Alice Smith worked on Project Phoenix last week.")
        assert any("Alice Smith" in n for n in result["names"])

    def test_empty_string_returns_empty_dict(self):
        from app.utils.entity_extractor import extract_entities

        result = extract_entities("")
        assert result == {}

    def test_no_false_positive_for_common_sentence_start(self):
        """Common sentence starters should not appear as proper nouns."""
        from app.utils.entity_extractor import extract_entities

        # "The system" should NOT produce "The System" as a name
        result = extract_entities("The system is working fine today.")
        names = result.get("names", [])
        assert not any(n.startswith("The ") for n in names)

    def test_deduplication(self):
        from app.utils.entity_extractor import extract_entities

        result = extract_entities("alice@example.com and alice@example.com again.")
        assert result["emails"].count("alice@example.com") == 1


@pytest.mark.unit
class TestEntityMerge:
    """Unit tests for merge_entities helper."""

    def test_merge_into_none(self):
        from app.utils.entity_extractor import merge_entities

        result = merge_entities(None, {"emails": ["a@b.com"]})
        assert result == {"emails": ["a@b.com"]}

    def test_merge_adds_new_values(self):
        from app.utils.entity_extractor import merge_entities

        existing = {"emails": ["a@b.com"]}
        new = {"emails": ["c@d.com"], "urls": ["https://x.com"]}
        result = merge_entities(existing, new)
        assert "a@b.com" in result["emails"]
        assert "c@d.com" in result["emails"]
        assert "https://x.com" in result["urls"]

    def test_merge_deduplicates(self):
        from app.utils.entity_extractor import merge_entities

        existing = {"emails": ["a@b.com"]}
        new = {"emails": ["a@b.com"]}
        result = merge_entities(existing, new)
        assert result["emails"].count("a@b.com") == 1


@pytest.mark.unit
class TestEntityExtractionInUpsert:
    """Verify entity extraction is wired into MemoryService.upsert()."""

    def test_entity_extractor_imported_in_memory_service(self):
        """The import must exist — checks wiring without running the DB."""
        import app.services.memory_service as svc_mod

        assert hasattr(svc_mod, "extract_entities")
        assert hasattr(svc_mod, "merge_entities")

    def test_extract_entities_callable(self):
        from app.utils.entity_extractor import extract_entities

        assert callable(extract_entities)

    def test_entities_stored_in_payload_key(self):
        """End-to-end: extract + merge returns __entities__ key."""
        from app.utils.entity_extractor import extract_entities, merge_entities

        content = "Email bob@acme.com about Project Delta by 2024-06-01."
        entities = extract_entities(content)
        payload: dict = {}
        payload["__entities__"] = merge_entities(payload.get("__entities__"), entities)

        assert "__entities__" in payload
        assert "bob@acme.com" in payload["__entities__"]["emails"]
        assert any("2024-06-01" in d for d in payload["__entities__"]["dates"])
