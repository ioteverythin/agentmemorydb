"""Unit tests for scoring utilities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.utils.scoring import (
    compute_final_score,
    compute_recency_score,
    normalize_authority,
)


@pytest.mark.unit
class TestRecencyScore:
    def test_just_now_is_one(self):
        now = datetime.now(UTC)
        score = compute_recency_score(now, now=now)
        assert abs(score - 1.0) < 1e-6

    def test_half_life_gives_half(self):
        now = datetime.now(UTC)
        past = now - timedelta(hours=72)
        score = compute_recency_score(past, now=now, half_life_hours=72.0)
        assert abs(score - 0.5) < 0.01

    def test_very_old_approaches_zero(self):
        now = datetime.now(UTC)
        past = now - timedelta(days=365)
        score = compute_recency_score(past, now=now)
        assert score < 0.01


@pytest.mark.unit
class TestNormalizeAuthority:
    def test_level_1(self):
        assert normalize_authority(1) == 0.25

    def test_level_4(self):
        assert normalize_authority(4) == 1.0

    def test_clamps_above(self):
        assert normalize_authority(10) == 1.0

    def test_clamps_below(self):
        assert normalize_authority(0) == 0.25


@pytest.mark.unit
class TestFinalScore:
    def test_with_vector(self):
        final, breakdown = compute_final_score(
            vector_similarity=0.9,
            recency_score=0.8,
            importance_score=0.7,
            authority_level=3,
            confidence=0.85,
        )
        assert 0 < final <= 1.0
        assert breakdown["vector_score"] == 0.9
        assert "final_score" in breakdown

    def test_without_vector_redistributes_weight(self):
        final, breakdown = compute_final_score(
            vector_similarity=None,
            recency_score=1.0,
            importance_score=1.0,
            authority_level=4,
            confidence=1.0,
        )
        # All non-vector components at max → score should be ~1.0
        assert abs(final - 1.0) < 0.01
        assert breakdown["vector_score"] is None

    def test_zero_scores(self):
        final, _ = compute_final_score(
            vector_similarity=0.0,
            recency_score=0.0,
            importance_score=0.0,
            authority_level=1,
            confidence=0.0,
        )
        # Only authority contributes (0.10 * 0.25 = 0.025)
        assert final < 0.05
