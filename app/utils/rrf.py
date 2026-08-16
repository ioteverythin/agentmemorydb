"""Reciprocal Rank Fusion (RRF) for combining ranked result lists.

RRF merges several independently-ranked lists (e.g. dense vector similarity
and sparse BM25/full-text) into one ranking without needing to calibrate the
raw scores of each source against each other. Each list contributes
``1 / (k + rank)`` to every item it contains; contributions are summed.

Reference: Cormack, Clarke & Buettcher, "Reciprocal Rank Fusion outperforms
Condorcet and individual Rank Learning Methods" (SIGIR 2009).
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[Hashable]],
    *,
    k: int = 60,
) -> dict[Hashable, float]:
    """Fuse multiple ranked lists of ids into a single ``{id: rrf_score}`` map.

    Args:
        rankings: A sequence of ranked lists. Each inner list is ordered best
            (index 0) to worst. Ids may appear in any subset of the lists.
        k: The RRF damping constant. Larger values flatten the contribution of
            top ranks relative to the tail. 60 is the standard default.

    Returns:
        A dict mapping each id seen in any list to its summed RRF score. Higher
        is better. Ids appearing near the top of multiple lists score highest.
    """
    if k < 1:
        raise ValueError("RRF k must be >= 1")

    scores: dict[Hashable, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank + 1)
    return scores


def fuse_and_order(
    rankings: Sequence[Sequence[Hashable]],
    *,
    k: int = 60,
) -> list[Hashable]:
    """Return ids ordered by descending fused RRF score.

    Ties are broken deterministically by first appearance across the input
    rankings, so the output is stable for identical inputs.
    """
    scores = reciprocal_rank_fusion(rankings, k=k)

    # Deterministic tie-break: first-seen order.
    first_seen: dict[Hashable, int] = {}
    counter = 0
    for ranking in rankings:
        for item in ranking:
            if item not in first_seen:
                first_seen[item] = counter
                counter += 1

    return sorted(scores, key=lambda item: (-scores[item], first_seen[item]))
