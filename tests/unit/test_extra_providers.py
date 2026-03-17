"""Unit tests for extra embedding providers (Ollama / SentenceTransformers / Cohere)."""

from __future__ import annotations

import pytest

from app.utils.extra_providers import OllamaEmbeddingProvider

try:
    from sentence_transformers import SentenceTransformer  # noqa: F401

    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False


@pytest.mark.unit
@pytest.mark.skipif(not HAS_SENTENCE_TRANSFORMERS, reason="sentence-transformers not installed")
class TestSentenceTransformerProvider:
    """Test that the provider initialises correctly."""

    def test_dimension(self):
        """Default dimension for all-MiniLM-L6-v2 is 384."""
        from app.utils.extra_providers import SentenceTransformerProvider

        provider = SentenceTransformerProvider()
        assert provider.dimension() == 384

    def test_custom_model(self):
        from app.utils.extra_providers import SentenceTransformerProvider

        provider = SentenceTransformerProvider(model_name="all-MiniLM-L6-v2")
        assert provider.dimension() == 384


@pytest.mark.unit
class TestOllamaProviderConfig:
    def test_default_config(self):
        p = OllamaEmbeddingProvider()
        assert "localhost" in p._base_url
        assert p._model == "nomic-embed-text"

    def test_custom_config(self):
        p = OllamaEmbeddingProvider(
            base_url="http://gpu-server:11434",
            model="mxbai-embed-large",
        )
        assert p._base_url == "http://gpu-server:11434"
        assert p._model == "mxbai-embed-large"

    def test_dimension(self):
        p = OllamaEmbeddingProvider(dim=768)
        assert p.dimension() == 768
