"""Vector similarity, computed in Python.

pgvector does this in SQL, and retrieval uses it there. But several features need
a similarity between two vectors *already loaded into memory* — comparing a new
write against candidates, scoring cluster membership, deciding whether two
memories deserve a link — and issuing a query per pair to get a number we can
compute in microseconds would be absurd. This also keeps those features working
on the SQLite test harness, which has no vector operators at all.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def cosine_similarity(a: Sequence[float] | None, b: Sequence[float] | None) -> float:
    """Cosine similarity of two vectors, in ``[-1, 1]``.

    Returns ``0.0`` — "unrelated" — rather than raising for the degenerate cases:
    a missing vector (a memory written before an embedding provider was
    configured), a zero vector, or a length mismatch (two memories embedded by
    different models). Treating a mismatch as unrelated is the safe direction:
    callers use this to decide whether to link, dispute, or cluster, and a
    fabricated similarity between incomparable vectors would drive all three
    wrong.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(dot / (norm_a * norm_b))
