"""Tests for the pure distillation strategy and retention scoring."""

from __future__ import annotations

import pytest

from app.utils.distillers import DistillItem, HeuristicDistiller
from app.utils.scoring import compute_retention_score, normalize_access


def _item(key, content, importance=0.5, layer="atom", payload=None):
    return DistillItem(
        memory_key=key,
        content=content,
        importance_score=importance,
        layer=layer,
        payload=payload,
    )


@pytest.mark.unit
class TestHeuristicDistiller:
    d = HeuristicDistiller()

    def test_topic_from_key_namespace(self):
        assert self.d.topic_of(_item("pref:language", "x")) == "pref"
        assert self.d.topic_of(_item("fact/role", "x")) == "fact"

    def test_topic_from_payload_wins(self):
        assert self.d.topic_of(_item("pref:x", "y", payload={"topic": "coding"})) == "coding"

    def test_topic_default(self):
        assert self.d.topic_of(_item("nokey", "y")) == "general"

    def test_scenario_digest_orders_by_importance(self):
        atoms = [
            _item("a", "less important", importance=0.2),
            _item("b", "most important", importance=0.9),
        ]
        digest = self.d.scenario_digest("pref", atoms, char_budget=1000)
        assert digest.startswith("Scenario · pref")
        assert digest.index("most important") < digest.index("less important")

    def test_scenario_digest_dedups(self):
        atoms = [_item("a", "same fact"), _item("b", "same fact")]
        digest = self.d.scenario_digest("t", atoms, char_budget=1000)
        assert digest.count("same fact") == 1

    def test_scenario_digest_respects_budget(self):
        atoms = [_item(str(i), "x" * 50, importance=1.0 - i / 100) for i in range(20)]
        digest = self.d.scenario_digest("t", atoms, char_budget=120)
        assert len(digest) <= 120

    def test_persona_synthesis(self):
        blocks = [_item("scenario:pref", "Scenario · pref\n- likes python", layer="scenario")]
        persona = self.d.persona_synthesis(blocks, char_budget=1000)
        assert persona.startswith("User profile")
        assert "python" in persona


@pytest.mark.unit
class TestRetentionScoring:
    def test_normalize_access_monotonic_and_saturating(self):
        assert normalize_access(0) == 0.0
        assert normalize_access(1) > 0
        assert normalize_access(5) > normalize_access(1)
        assert normalize_access(1000, saturation=20) == 1.0

    def test_frequent_access_beats_stale_low_importance(self):
        # Stale + low importance, but hot → should retain more than cold junk.
        hot = compute_retention_score(recency_score=0.1, importance_score=0.2, access_count=15)
        cold = compute_retention_score(recency_score=0.1, importance_score=0.2, access_count=0)
        assert hot > cold

    def test_recent_important_scores_high(self):
        s = compute_retention_score(recency_score=1.0, importance_score=1.0, access_count=10)
        assert s > 0.8

    def test_weights_applied(self):
        s = compute_retention_score(
            recency_score=1.0,
            importance_score=0.0,
            access_count=0,
            weight_recency=1.0,
            weight_importance=0.0,
            weight_access=0.0,
        )
        assert s == pytest.approx(1.0)
