"""Pluggable embedding provider abstraction."""

from __future__ import annotations

import abc

import numpy as np

from app.core.config import settings


class BaseEmbeddingProvider(abc.ABC):
    """Interface that all embedding providers must implement."""

    @abc.abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""

    @abc.abstractmethod
    def dimension(self) -> int:
        """Return the embedding dimension this provider produces."""


class DummyEmbeddingProvider(BaseEmbeddingProvider):
    """Deterministic fake embeddings for local development / tests.

    Produces unit-length vectors derived from a hash of the input text
    so that identical strings always yield the same embedding and
    semantically similar strings have *some* overlap (via character-level
    hashing into random buckets).
    """

    def __init__(self, dim: int | None = None) -> None:
        self._dim = dim or settings.embedding_dimension

    def dimension(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            rng = np.random.default_rng(seed=abs(hash(text)) % (2**32))
            vec = rng.standard_normal(self._dim).astype(float)
            norm = float(np.linalg.norm(vec))
            if norm > 0:
                vec = vec / norm
            results.append(vec.tolist())
        return results


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """Placeholder for OpenAI embedding integration.

    Requires ``openai`` extra: ``pip install agentmemorydb[openai]``
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        dim: int | None = None,
    ) -> None:
        self._api_key = api_key or settings.openai_api_key
        self._model = model or settings.openai_embedding_model
        self._dim = dim or settings.embedding_dimension
        if not self._api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY or pass api_key.")

    def dimension(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Lazy import so the dep is optional
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError(
                "Install the openai extra: pip install agentmemorydb[openai]"
            ) from exc

        client = AsyncOpenAI(api_key=self._api_key)
        response = await client.embeddings.create(input=texts, model=self._model)
        return [item.embedding for item in response.data]


# ── Factory ─────────────────────────────────────────────────────
_provider: BaseEmbeddingProvider | None = None


def get_embedding_provider() -> BaseEmbeddingProvider:
    """Return the configured embedding provider (singleton)."""
    global _provider
    if _provider is None:
        if settings.openai_api_key:
            _provider = OpenAIEmbeddingProvider()
        else:
            _provider = DummyEmbeddingProvider()
    return _provider


def set_embedding_provider(provider: BaseEmbeddingProvider) -> None:
    """Override the global embedding provider (useful for tests)."""
    global _provider
    _provider = provider
