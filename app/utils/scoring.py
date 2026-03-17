"""Scoring utilities for hybrid memory retrieval."""

from __future__ import annotations

import math
from datetime import UTC, datetime

from app.core.config import settings


def compute_recency_score(
    updated_at: datetime,
    now: datetime | None = None,
    half_life_hours: float = 72.0,
) -> float:
    """Exponential decay recency score.

    Returns a value in [0, 1] where 1 means *just now* and the score
    halves every ``half_life_hours``.
    """
    if now is None:
        now = datetime.now(UTC)
    # Ensure both are offset-aware
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    age_hours = max((now - updated_at).total_seconds() / 3600.0, 0.0)
    return math.exp(-math.log(2) * age_hours / half_life_hours)


def normalize_authority(authority_level: int, max_level: int = 4) -> float:
    """Normalize authority_level (1–4) to [0, 1]."""
    return min(max(authority_level, 1), max_level) / max_level


def compute_final_score(
    *,
    vector_similarity: float | None = None,
    recency_score: float,
    importance_score: float,
    authority_level: int,
    confidence: float,
) -> tuple[float, dict[str, float]]:
    """Compute a weighted final score and return a component breakdown.

    Scoring formula:
        final = w_v * vector_sim + w_r * recency + w_i * importance
                + w_a * authority_norm + w_c * confidence

    If no vector similarity is available the weight is redistributed
    proportionally across the remaining components.
    """
    w_v = settings.score_weight_vector
    w_r = settings.score_weight_recency
    w_i = settings.score_weight_importance
    w_a = settings.score_weight_authority
    w_c = settings.score_weight_confidence

    authority_norm = normalize_authority(authority_level)

    if vector_similarity is None:
        # Redistribute vector weight proportionally
        remaining = w_r + w_i + w_a + w_c
        if remaining > 0:
            scale = (w_v + remaining) / remaining
            w_r *= scale
            w_i *= scale
            w_a *= scale
            w_c *= scale
        w_v = 0.0
        vec_score = 0.0
    else:
        vec_score = max(min(vector_similarity, 1.0), 0.0)

    final = (
        w_v * vec_score
        + w_r * recency_score
        + w_i * importance_score
        + w_a * authority_norm
        + w_c * confidence
    )

    breakdown = {
        "vector_score": vec_score if vector_similarity is not None else None,  # type: ignore[dict-item]
        "recency_score": recency_score,
        "importance_score": importance_score,
        "authority_score": authority_norm,
        "confidence_score": confidence,
        "final_score": round(final, 6),
    }
    return round(final, 6), breakdown
