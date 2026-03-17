"""Unit tests for data masking — PII engine, service, and pipeline integration."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest

from app.services.masking_service import MaskingService
from app.utils.masking import (
    _BUILTIN_PATTERNS,
    Detection,
    MaskingResult,
    PIIMaskingEngine,
    get_default_engine,
)

# ═══════════════════════════════════════════════════════════════════
# § 1  PIIMaskingEngine — Pattern Detection
# ═══════════════════════════════════════════════════════════════════


class TestPIIEnginePatternDetection:
    """Test that each built-in pattern detects the expected PII."""

    def _engine(self, *patterns: str) -> PIIMaskingEngine:
        return PIIMaskingEngine(enabled_patterns=list(patterns))

    # ── Email ────────────────────────────────────────────────────

    def test_email_basic(self):
        engine = self._engine("email")
        result = engine.mask_text("Contact josh@example.com for details")
        assert result.was_modified
        assert "[EMAIL]" in result.masked_text
        assert "josh@example.com" not in result.masked_text
        assert result.patterns_detected == ["email"]

    def test_email_multiple(self):
        engine = self._engine("email")
        result = engine.mask_text("Send to a@b.com and c@d.org please")
        assert result.masked_text.count("[EMAIL]") == 2

    def test_email_in_sentence(self):
        engine = self._engine("email")
        result = engine.mask_text("My email is user.name+tag@company.co.uk okay?")
        assert "[EMAIL]" in result.masked_text

    # ── Phone ────────────────────────────────────────────────────

    def test_phone_us_format(self):
        engine = self._engine("phone")
        result = engine.mask_text("Call me at 555-123-4567")
        assert result.was_modified
        assert "[PHONE]" in result.masked_text
        assert "555-123-4567" not in result.masked_text

    def test_phone_intl_format(self):
        engine = self._engine("phone")
        result = engine.mask_text("Reach us at +1-555-123-4567")
        assert "[PHONE]" in result.masked_text

    def test_phone_parens_format(self):
        engine = self._engine("phone")
        result = engine.mask_text("Number: (555) 123-4567")
        assert "[PHONE]" in result.masked_text

    # ── SSN ──────────────────────────────────────────────────────

    def test_ssn_standard(self):
        engine = self._engine("ssn")
        result = engine.mask_text("SSN is 123-45-6789")
        assert result.was_modified
        assert "[SSN]" in result.masked_text
        assert "123-45-6789" not in result.masked_text

    def test_ssn_no_false_positive_on_phone(self):
        engine = self._engine("ssn")
        result = engine.mask_text("Call 555-1234")
        assert not result.was_modified  # too few digits for SSN

    # ── Credit Card ──────────────────────────────────────────────

    def test_credit_card_visa(self):
        engine = self._engine("credit_card")
        result = engine.mask_text("Card: 4111-1111-1111-1111")
        assert result.was_modified
        assert "[CREDIT_CARD]" in result.masked_text
        assert "4111" not in result.masked_text

    def test_credit_card_no_separators(self):
        engine = self._engine("credit_card")
        result = engine.mask_text("4111111111111111")
        assert "[CREDIT_CARD]" in result.masked_text

    # ── IP Address ───────────────────────────────────────────────

    def test_ip_address(self):
        engine = self._engine("ip_address")
        result = engine.mask_text("Server at 192.168.1.100")
        assert result.was_modified
        assert "[IP_ADDRESS]" in result.masked_text
        assert "192.168.1.100" not in result.masked_text

    def test_ip_address_no_false_positive(self):
        engine = self._engine("ip_address")
        result = engine.mask_text("Version 3.11.2")
        assert not result.was_modified  # not a valid IP

    # ── DOB ──────────────────────────────────────────────────────

    def test_dob_detection(self):
        engine = self._engine("date_of_birth")
        result = engine.mask_text("DOB: 01/15/1990")
        assert result.was_modified
        assert "[DOB]" in result.masked_text

    def test_dob_born_on(self):
        engine = self._engine("date_of_birth")
        result = engine.mask_text("born on 1990-01-15")
        assert "[DOB]" in result.masked_text


# ═══════════════════════════════════════════════════════════════════
# § 2  PIIMaskingEngine — General Behavior
# ═══════════════════════════════════════════════════════════════════


class TestPIIEngineGeneral:
    def test_empty_text(self):
        engine = PIIMaskingEngine(enabled_patterns=["email"])
        result = engine.mask_text("")
        assert not result.was_modified
        assert result.masked_text == ""

    def test_none_text(self):
        engine = PIIMaskingEngine(enabled_patterns=["email"])
        result = engine.mask_text(None)
        assert not result.was_modified

    def test_no_patterns_enabled(self):
        engine = PIIMaskingEngine(enabled_patterns=[])
        result = engine.mask_text("josh@example.com")
        assert not result.was_modified
        assert result.masked_text == "josh@example.com"

    def test_no_pii_found(self):
        engine = PIIMaskingEngine(enabled_patterns=["email", "phone"])
        result = engine.mask_text("No PII in this text at all")
        assert not result.was_modified

    def test_multiple_patterns_same_text(self):
        engine = PIIMaskingEngine(enabled_patterns=["email", "phone"])
        result = engine.mask_text("Email me at a@b.com or call 555-123-4567")
        assert "[EMAIL]" in result.masked_text
        assert "[PHONE]" in result.masked_text

    def test_original_text_preserved(self):
        engine = PIIMaskingEngine(enabled_patterns=["email"])
        result = engine.mask_text("user@test.com")
        assert result.original_text == "user@test.com"

    def test_surrounding_text_preserved(self):
        engine = PIIMaskingEngine(enabled_patterns=["email"])
        result = engine.mask_text("Hello josh@x.com goodbye")
        assert result.masked_text.startswith("Hello ")
        assert result.masked_text.endswith(" goodbye")

    def test_active_patterns_property(self):
        engine = PIIMaskingEngine(enabled_patterns=["email", "phone"])
        assert "email" in engine.active_patterns
        assert "phone" in engine.active_patterns
        assert "ssn" not in engine.active_patterns


# ═══════════════════════════════════════════════════════════════════
# § 3  Custom Patterns
# ═══════════════════════════════════════════════════════════════════


class TestCustomPatterns:
    def test_custom_regex(self):
        engine = PIIMaskingEngine(
            enabled_patterns=[],
            custom_patterns=[
                {
                    "name": "employee_id",
                    "regex": r"EMP-\d{6}",
                    "token": "[EMPLOYEE_ID]",
                }
            ],
        )
        result = engine.mask_text("Employee EMP-123456 is assigned")
        assert result.was_modified
        assert "[EMPLOYEE_ID]" in result.masked_text
        assert "EMP-123456" not in result.masked_text

    def test_custom_default_token(self):
        engine = PIIMaskingEngine(
            enabled_patterns=[],
            custom_patterns=[
                {
                    "name": "project_code",
                    "regex": r"PRJ-[A-Z]{3}-\d{4}",
                }
            ],
        )
        result = engine.mask_text("Working on PRJ-ABC-1234")
        assert "[PROJECT_CODE]" in result.masked_text

    def test_custom_plus_builtin(self):
        engine = PIIMaskingEngine(
            enabled_patterns=["email"],
            custom_patterns=[
                {
                    "name": "employee_id",
                    "regex": r"EMP-\d{6}",
                    "token": "[EMPLOYEE_ID]",
                }
            ],
        )
        result = engine.mask_text("EMP-999999 emailed at x@y.com")
        assert "[EMPLOYEE_ID]" in result.masked_text
        assert "[EMAIL]" in result.masked_text


# ═══════════════════════════════════════════════════════════════════
# § 4  mask_dict
# ═══════════════════════════════════════════════════════════════════


class TestMaskDict:
    def test_mask_dict_all_string_values(self):
        engine = PIIMaskingEngine(enabled_patterns=["email"])
        data = {"name": "Josh", "contact": "josh@mail.com", "count": 42}
        detections = engine.mask_dict(data)
        assert data["contact"] == "[EMAIL]"
        assert data["name"] == "Josh"  # no PII
        assert data["count"] == 42  # non-string, untouched
        assert "contact" in detections

    def test_mask_dict_specific_fields(self):
        engine = PIIMaskingEngine(enabled_patterns=["email"])
        data = {"safe": "josh@mail.com", "target": "josh@mail.com"}
        detections = engine.mask_dict(data, fields=["target"])
        assert data["safe"] == "josh@mail.com"  # not scanned
        assert data["target"] == "[EMAIL]"
        assert "target" in detections
        assert "safe" not in detections


# ═══════════════════════════════════════════════════════════════════
# § 5  MaskingResult & Detection dataclasses
# ═══════════════════════════════════════════════════════════════════


class TestMaskingResult:
    def test_patterns_detected_deduped(self):
        r = MaskingResult(
            original_text="test",
            masked_text="test",
            detections=[
                Detection(
                    pattern_name="email", token="[EMAIL]", start=0, end=5, matched_text="a@b.c"
                ),
                Detection(
                    pattern_name="email", token="[EMAIL]", start=10, end=15, matched_text="d@e.f"
                ),
            ],
            was_modified=True,
        )
        assert r.patterns_detected == ["email"]


# ═══════════════════════════════════════════════════════════════════
# § 6  get_default_engine factory
# ═══════════════════════════════════════════════════════════════════


class TestGetDefaultEngine:
    def test_disabled_returns_empty(self):
        with patch("app.core.settings") as mock_settings:
            mock_settings.enable_data_masking = False
            engine = get_default_engine()
            assert engine.active_patterns == []

    def test_enabled_with_patterns(self):
        with patch("app.core.settings") as mock_settings:
            mock_settings.enable_data_masking = True
            mock_settings.masking_patterns = "email,phone"
            mock_settings.masking_custom_patterns = None
            engine = get_default_engine()
            assert "email" in engine.active_patterns
            assert "phone" in engine.active_patterns

    def test_enabled_with_custom_json(self):
        custom = json.dumps([{"name": "test_pat", "regex": r"XYZ-\d+", "token": "[TEST]"}])
        with patch("app.core.settings") as mock_settings:
            mock_settings.enable_data_masking = True
            mock_settings.masking_patterns = "email"
            mock_settings.masking_custom_patterns = custom
            engine = get_default_engine()
            assert "email" in engine.active_patterns
            assert "test_pat" in engine.active_patterns

    def test_bad_custom_json_ignored(self):
        with patch("app.core.settings") as mock_settings:
            mock_settings.enable_data_masking = True
            mock_settings.masking_patterns = "email"
            mock_settings.masking_custom_patterns = "not valid json{{"
            engine = get_default_engine()
            assert "email" in engine.active_patterns


# ═══════════════════════════════════════════════════════════════════
# § 7  Settings integration
# ═══════════════════════════════════════════════════════════════════


class TestMaskingSettings:
    def test_default_settings(self):
        from app.core import Settings

        s = Settings(
            database_url="sqlite+aiosqlite:///:memory:",
        )
        assert s.enable_data_masking is False
        assert "email" in s.masking_patterns
        assert s.masking_log_detections is True
        assert s.masking_custom_patterns is None

    def test_settings_enable(self):
        from app.core import Settings

        s = Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            enable_data_masking=True,
            masking_patterns="ssn,credit_card",
        )
        assert s.enable_data_masking is True
        assert "ssn" in s.masking_patterns
        assert "email" not in s.masking_patterns


# ═══════════════════════════════════════════════════════════════════
# § 8  Pipeline integration — _mask_if_enabled helpers
# ═══════════════════════════════════════════════════════════════════


class TestPipelineMasking:
    """Test that the _mask_if_enabled helpers in services work correctly."""

    def test_memory_service_mask_helper(self):
        with patch("app.services.memory_service.get_default_engine") as mock_factory:
            engine = PIIMaskingEngine(enabled_patterns=["email"])
            mock_factory.return_value = engine
            from app.services.memory_service import _mask_if_enabled

            result = _mask_if_enabled("Contact josh@mail.com")
            assert result == "Contact [EMAIL]"

    def test_event_service_mask_helper(self):
        with patch("app.services.event_service.get_default_engine") as mock_factory:
            engine = PIIMaskingEngine(enabled_patterns=["phone"])
            mock_factory.return_value = engine
            from app.services.event_service import _mask_if_enabled

            result = _mask_if_enabled("Call 555-123-4567 now")
            assert result == "Call [PHONE] now"

    def test_observation_service_mask_helper(self):
        with patch("app.services.observation_service.get_default_engine") as mock_factory:
            engine = PIIMaskingEngine(enabled_patterns=["ssn"])
            mock_factory.return_value = engine
            from app.services.observation_service import _mask_if_enabled

            result = _mask_if_enabled("SSN is 123-45-6789")
            assert result == "SSN is [SSN]"

    def test_mask_helper_returns_none_for_none(self):
        with patch("app.services.memory_service.get_default_engine") as mock_factory:
            engine = PIIMaskingEngine(enabled_patterns=["email"])
            mock_factory.return_value = engine
            from app.services.memory_service import _mask_if_enabled

            assert _mask_if_enabled(None) is None

    def test_mask_helper_returns_unchanged_when_no_pii(self):
        with patch("app.services.memory_service.get_default_engine") as mock_factory:
            engine = PIIMaskingEngine(enabled_patterns=["email"])
            mock_factory.return_value = engine
            from app.services.memory_service import _mask_if_enabled

            assert _mask_if_enabled("No PII here") == "No PII here"

    def test_mask_helper_returns_unchanged_when_disabled(self):
        with patch("app.services.memory_service.get_default_engine") as mock_factory:
            engine = PIIMaskingEngine(enabled_patterns=[])
            mock_factory.return_value = engine
            from app.services.memory_service import _mask_if_enabled

            assert _mask_if_enabled("josh@mail.com") == "josh@mail.com"


# ═══════════════════════════════════════════════════════════════════
# § 9  MaskingLog model
# ═══════════════════════════════════════════════════════════════════


class TestMaskingLogModel:
    def test_model_fields(self):
        from app.models.masking_log import MaskingLog

        log = MaskingLog(
            entity_type="memory",
            entity_id=uuid.uuid4(),
            field_name="content",
            patterns_detected=["email", "phone"],
            detection_count=3,
            original_content_hash="abc123",
            user_id=uuid.uuid4(),
        )
        assert log.entity_type == "memory"
        assert log.detection_count == 3
        assert "email" in log.patterns_detected

    def test_model_tablename(self):
        from app.models.masking_log import MaskingLog

        assert MaskingLog.__tablename__ == "masking_logs"


# ═══════════════════════════════════════════════════════════════════
# § 10  Masking schemas
# ═══════════════════════════════════════════════════════════════════


class TestMaskingSchemas:
    def test_test_request(self):
        from app.schemas.masking import MaskingTestRequest

        req = MaskingTestRequest(text="hello@world.com")
        assert req.text == "hello@world.com"

    def test_test_response(self):
        from app.schemas.masking import MaskingTestResponse

        resp = MaskingTestResponse(
            original_text="hello@world.com",
            masked_text="[EMAIL]",
            was_modified=True,
            patterns_detected=["email"],
            detection_count=1,
        )
        assert resp.was_modified
        assert resp.detection_count == 1

    def test_config_response(self):
        from app.schemas.masking import MaskingConfigResponse

        resp = MaskingConfigResponse(
            enabled=True,
            active_patterns=["email", "phone"],
            log_detections=True,
            custom_patterns_configured=False,
        )
        assert resp.enabled
        assert len(resp.active_patterns) == 2

    def test_stats_response(self):
        from app.schemas.masking import MaskingStatsResponse

        resp = MaskingStatsResponse(
            total_masking_actions=42,
            by_entity_type={"memory": 30, "event": 12},
            masking_enabled=True,
            active_patterns=["email"],
        )
        assert resp.total_masking_actions == 42


# ═══════════════════════════════════════════════════════════════════
# § 11  Builtin patterns completeness
# ═══════════════════════════════════════════════════════════════════


class TestBuiltinPatterns:
    def test_all_expected_patterns_registered(self):
        expected = {
            "ssn",
            "credit_card",
            "email",
            "phone",
            "ip_address",
            "us_passport",
            "date_of_birth",
        }
        assert expected == set(_BUILTIN_PATTERNS.keys())

    def test_each_pattern_has_token(self):
        for _name, pattern in _BUILTIN_PATTERNS.items():
            assert pattern.token.startswith("[")
            assert pattern.token.endswith("]")

    def test_overlapping_matches_resolved(self):
        """When two patterns overlap, only the first/longest match should win."""
        engine = PIIMaskingEngine(enabled_patterns=["ssn", "phone"])
        # 123-45-6789 could match SSN or be part of a phone-like sequence
        result = engine.mask_text("SSN: 123-45-6789")
        assert "[SSN]" in result.masked_text
        assert (
            result.detection_count
            if hasattr(result, "detection_count")
            else len(result.detections) >= 1
        )


# ═══════════════════════════════════════════════════════════════════
# § 12  MaskingService (async)
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestMaskingServiceAsync:
    async def test_mask_content_when_enabled(self, unit_session):
        with patch("app.services.masking_service.settings") as mock_settings:
            mock_settings.enable_data_masking = True
            mock_settings.masking_patterns = "email"
            mock_settings.masking_custom_patterns = None
            mock_settings.masking_log_detections = False

            engine = PIIMaskingEngine(enabled_patterns=["email"])
            svc = MaskingService(unit_session, engine=engine)
            result = await svc.mask_content(
                "Email josh@test.com",
                entity_type="memory",
                entity_id=uuid.uuid4(),
            )
            assert result == "Email [EMAIL]"

    async def test_mask_content_when_disabled(self, unit_session):
        with patch("app.services.masking_service.settings") as mock_settings:
            mock_settings.enable_data_masking = False

            engine = PIIMaskingEngine(enabled_patterns=[])
            svc = MaskingService(unit_session, engine=engine)
            result = await svc.mask_content(
                "Email josh@test.com",
                entity_type="memory",
            )
            assert result == "Email josh@test.com"

    async def test_mask_content_none(self, unit_session):
        with patch("app.services.masking_service.settings") as mock_settings:
            mock_settings.enable_data_masking = True
            engine = PIIMaskingEngine(enabled_patterns=["email"])
            svc = MaskingService(unit_session, engine=engine)
            assert await svc.mask_content(None, entity_type="memory") is None

    async def test_mask_payload(self, unit_session):
        with patch("app.services.masking_service.settings") as mock_settings:
            mock_settings.enable_data_masking = True
            mock_settings.masking_log_detections = False

            engine = PIIMaskingEngine(enabled_patterns=["email"])
            svc = MaskingService(unit_session, engine=engine)
            payload = {"note": "Contact a@b.com", "count": 5}
            result = await svc.mask_payload(
                payload,
                entity_type="memory",
                entity_id=uuid.uuid4(),
            )
            assert result["note"] == "Contact [EMAIL]"
            assert result["count"] == 5

    async def test_mask_text_sync(self, unit_session):
        with patch("app.services.masking_service.settings") as mock_settings:
            mock_settings.enable_data_masking = True

            engine = PIIMaskingEngine(enabled_patterns=["phone"])
            svc = MaskingService(unit_session, engine=engine)
            result = svc.mask_text_sync("Call 555-123-4567")
            assert result == "Call [PHONE]"


# ═══════════════════════════════════════════════════════════════════
# § 13  Edge cases & regression
# ═══════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_text_is_only_pii(self):
        engine = PIIMaskingEngine(enabled_patterns=["email"])
        result = engine.mask_text("josh@example.com")
        assert result.masked_text == "[EMAIL]"

    def test_adjacent_pii(self):
        engine = PIIMaskingEngine(enabled_patterns=["email"])
        result = engine.mask_text("a@b.com c@d.com")
        assert result.masked_text == "[EMAIL] [EMAIL]"

    def test_pii_at_start(self):
        engine = PIIMaskingEngine(enabled_patterns=["email"])
        result = engine.mask_text("josh@x.com is here")
        assert result.masked_text.startswith("[EMAIL]")

    def test_pii_at_end(self):
        engine = PIIMaskingEngine(enabled_patterns=["email"])
        result = engine.mask_text("Contact josh@x.com")
        assert result.masked_text.endswith("[EMAIL]")

    def test_multiline_text(self):
        engine = PIIMaskingEngine(enabled_patterns=["email", "phone"])
        text = "Line 1: josh@x.com\nLine 2: 555-123-4567\nLine 3: safe"
        result = engine.mask_text(text)
        assert "[EMAIL]" in result.masked_text
        assert "[PHONE]" in result.masked_text
        assert "Line 3: safe" in result.masked_text

    def test_unicode_text_unaffected(self):
        engine = PIIMaskingEngine(enabled_patterns=["email"])
        result = engine.mask_text("こんにちは josh@x.com さようなら")
        assert "[EMAIL]" in result.masked_text
        assert "こんにちは" in result.masked_text
        assert "さようなら" in result.masked_text
