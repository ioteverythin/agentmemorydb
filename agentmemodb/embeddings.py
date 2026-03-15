"""Embedding providers for the AgentMemoryDB embedded client.

Providers
---------
DummyEmbedding   – deterministic hash-based vectors (default, no API key)
OpenAIEmbedding  – OpenAI text-embedding models (requires ``pip install openai``)

Custom providers – any callable that matches the ``EmbeddingFunction`` protocol.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Protocol, runtime_checkable


# ── Protocol ────────────────────────────────────────────────────────


@runtime_checkable
class EmbeddingFunction(Protocol):
    """Minimal interface an embedding provider must satisfy."""

    def __call__(self, texts: list[str]) -> list[list[float]]: ...

    @property
    def dimension(self) -> int: ...


# ── Dummy (hash-based, zero-dependency) ─────────────────────────────


class DummyEmbedding:
    """SHA-256 hash → deterministic float vector.

    Good for deduplication and basic similarity (same text = same
    vector), but **not** semantically meaningful.  Use for testing
    or when no API key is available.
    """

    def __init__(self, dimension: int = 128) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def __call__(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_to_vector(t) for t in texts]

    def _hash_to_vector(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()
        # Repeat the 32-byte hash to fill *dimension* floats
        repeat = (self._dimension * 4 // len(h)) + 1
        raw = (h * repeat)[: self._dimension * 4]
        values = list(struct.unpack(f"<{self._dimension}f", raw))
        # L2-normalize
        norm = sum(v * v for v in values) ** 0.5
        if norm == 0:
            return [0.0] * self._dimension
        return [v / norm for v in values]


# ── OpenAI ──────────────────────────────────────────────────────────


class OpenAIEmbedding:
    """OpenAI-powered embeddings.

    Requires ``pip install agentmemodb[openai]`` (or ``pip install openai``).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "text-embedding-3-small",
        dimension: int = 1536,
    ) -> None:
        try:
            import openai  # noqa: F401
        except ImportError:
            raise ImportError(
                "The openai package is required for OpenAIEmbedding. "
                "Install it with:  pip install agentmemodb[openai]"
            ) from None

        import openai as _openai

        self._client = _openai.OpenAI(api_key=api_key)
        self._model = model
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def __call__(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(input=texts, model=self._model)
        return [item.embedding for item in resp.data]
