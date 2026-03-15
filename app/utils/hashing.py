"""Content hashing for deduplication."""

from __future__ import annotations

import hashlib


def compute_content_hash(content: str) -> str:
    """Return a stable SHA-256 hex digest for a content string.

    Used to detect duplicate memory content and for upsert dedup.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
