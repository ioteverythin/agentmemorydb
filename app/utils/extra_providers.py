"""Additional embedding providers: Cohere and local SentenceTransformers."""

from __future__ import annotations

import os
from typing import Any

from app.core.config import settings
from app.utils.embedding_provider import BaseEmbeddingProvider


class CohereEmbeddingProvider(BaseEmbeddingProvider):
    """Cohere embedding provider.

    Requires ``cohere`` package: ``pip install cohere``
    Set COHERE_API_KEY in environment.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "embed-english-v3.0",
        dim: int | None = None,
    ) -> None:
        self._api_key = api_key or getattr(settings, "cohere_api_key", None)
        self._model = model
        self._dim = dim or settings.embedding_dimension
        if not self._api_key:
            raise ValueError(
                "Cohere API key required. Set COHERE_API_KEY or pass api_key."
            )

    def dimension(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            import cohere
        except ImportError as exc:
            raise ImportError(
                "Install cohere: pip install cohere"
            ) from exc

        co = cohere.Client(self._api_key)
        response = co.embed(
            texts=texts,
            model=self._model,
            input_type="search_document",
        )
        return [list(emb) for emb in response.embeddings]


class SentenceTransformerProvider(BaseEmbeddingProvider):
    """Local embedding provider using sentence-transformers.

    Runs entirely on your machine — no API key needed.
    Requires ``sentence-transformers`` package.

    Default model: all-MiniLM-L6-v2 (384-dim, fast)
    For higher quality: all-mpnet-base-v2 (768-dim)
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        device: str | None = None,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "Install sentence-transformers: pip install sentence-transformers"
            ) from exc

        self._model = SentenceTransformer(
            model_name,
            device=device,
            cache_folder=os.environ.get("SENTENCE_TRANSFORMERS_HOME"),
        )
        self._dim = self._model.get_sentence_embedding_dimension()

    def dimension(self) -> int:
        return self._dim  # type: ignore[return-value]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # sentence-transformers is synchronous; run in thread
        import asyncio

        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None,
            lambda: self._model.encode(texts, normalize_embeddings=True).tolist(),
        )
        return embeddings  # type: ignore[return-value]


class OllamaEmbeddingProvider(BaseEmbeddingProvider):
    """Ollama local embedding provider.

    Uses the Ollama REST API for generating embeddings locally.
    Requires a running Ollama server.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        dim: int | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dim = dim or settings.embedding_dimension

    def dimension(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        results: list[list[float]] = []
        async with httpx.AsyncClient(timeout=60.0) as client:
            for text in texts:
                resp = await client.post(
                    f"{self._base_url}/api/embeddings",
                    json={"model": self._model, "prompt": text},
                )
                resp.raise_for_status()
                results.append(resp.json()["embedding"])
        return results
