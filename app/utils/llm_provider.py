"""Pluggable LLM providers, mirroring ``app.utils.embedding_provider``.

Features that *optionally* use an LLM (contradiction classification, reflection)
depend on this interface rather than any vendor SDK. The default
:class:`NullLLMProvider` is unavailable, so those features degrade gracefully —
skip and log — when no provider is configured. That keeps EngramDB usable with
zero API keys and vendor-neutral.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from app.core.config import settings

logger = logging.getLogger(__name__)


class BaseLLMProvider(ABC):
    """A minimal text-completion contract."""

    @property
    @abstractmethod
    def available(self) -> bool:
        """False when the provider cannot serve requests (missing key/dep)."""

    @abstractmethod
    async def complete(self, prompt: str, *, system: str | None = None) -> str:
        """Return the model's completion for ``prompt``."""

    @property
    def name(self) -> str:
        return type(self).__name__


class NullLLMProvider(BaseLLMProvider):
    """The default: no LLM configured. Callers must check ``available``."""

    @property
    def available(self) -> bool:
        return False

    async def complete(self, prompt: str, *, system: str | None = None) -> str:
        raise RuntimeError(
            "No LLM provider configured. Set LLM_PROVIDER (and its API key) to "
            "enable LLM-backed features."
        )


class OpenAILLMProvider(BaseLLMProvider):
    """OpenAI-compatible chat completions (also serves any compatible gateway)."""

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self._model = model or settings.llm_model
        self._api_key = api_key or settings.openai_api_key
        self._client = None

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    def _ensure_client(self):
        if self._client is None:
            from openai import AsyncOpenAI  # lazy: optional dependency

            self._client = AsyncOpenAI(api_key=self._api_key, base_url=settings.llm_base_url)
        return self._client

    async def complete(self, prompt: str, *, system: str | None = None) -> str:
        client = self._ensure_client()
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = await client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_seconds,
        )
        return (response.choices[0].message.content or "").strip()


# ── Module-level singleton (same shape as the embedding provider) ────

_provider: BaseLLMProvider | None = None


def get_llm_provider() -> BaseLLMProvider:
    """Return the active LLM provider, resolving from settings on first use."""
    global _provider
    if _provider is None:
        name = (settings.llm_provider or "none").lower()
        if name in ("openai", "openai-compatible") and settings.openai_api_key:
            _provider = OpenAILLMProvider()
        else:
            if name not in ("none", ""):
                logger.warning(
                    "LLM_PROVIDER=%s but no API key configured — LLM features disabled.", name
                )
            _provider = NullLLMProvider()
    return _provider


def set_llm_provider(provider: BaseLLMProvider) -> None:
    """Override the active provider (tests, or a custom implementation)."""
    global _provider
    _provider = provider
