"""Embedded AgentMemoryDB client — SQLite-backed, zero config.

Usage::

    import agentmemodb

    db = agentmemodb.Client()                       # default path
    db = agentmemodb.Client(path=":memory:")        # in-memory (tests)
    db = agentmemodb.Client(path="./my_memories")   # custom dir

    db.upsert("user-1", "pref:lang", "User prefers Python")
    results = db.search("user-1", "language?")
    for r in results:
        print(f"  {r.key}: {r.content}  (score={r.score:.3f})")
    db.close()

No PostgreSQL, no Docker, no server — everything runs in-process
with SQLite + NumPy.
"""

from __future__ import annotations

import os
from typing import Any

from agentmemodb.embeddings import DummyEmbedding, EmbeddingFunction
from agentmemodb.store import SQLiteStore
from agentmemodb.types import Memory, MemoryVersion, SearchResult


class Client:
    """In-process AgentMemoryDB backed by SQLite.

    Parameters
    ----------
    path
        File path for the SQLite database.
        ``None`` → ``./agentmemodb_data/agentmemodb.sqlite3``.
        ``":memory:"`` → purely in-memory (no disk I/O).
        A directory path → stores ``agentmemodb.sqlite3`` inside it.
    embedding_fn
        Any object satisfying the :class:`EmbeddingFunction` protocol.
        Defaults to :class:`DummyEmbedding` (hash-based, dimension 128).
    mask_pii
        When *True*, PII (emails, phones, SSNs, …) is stripped from
        content **before** storage using the built-in masking engine.
    """

    def __init__(
        self,
        path: str | None = None,
        embedding_fn: EmbeddingFunction | None = None,
        mask_pii: bool = False,
    ) -> None:
        # ── Resolve storage path ──
        if path is None:
            path = os.path.join(
                os.getcwd(), "agentmemodb_data", "agentmemodb.sqlite3"
            )
        elif path != ":memory:":
            if not path.endswith((".sqlite3", ".db")):
                path = os.path.join(path, "agentmemodb.sqlite3")

        self._embedding_fn = embedding_fn or DummyEmbedding()
        self._mask_pii = mask_pii
        self._masking_engine = None

        if mask_pii:
            from agentmemodb.masking import PIIMaskingEngine

            self._masking_engine = PIIMaskingEngine()

        self._store = SQLiteStore(
            path=path, dimension=self._embedding_fn.dimension
        )

    # ── Internal helpers ────────────────────────────────────────

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return self._embedding_fn(texts)

    def _mask(self, text: str) -> str:
        if self._masking_engine:
            return self._masking_engine.mask_text(text).masked_text
        return text

    # ── Core API ────────────────────────────────────────────────

    def upsert(
        self,
        user_id: str,
        key: str,
        content: str,
        *,
        memory_type: str = "semantic",
        scope: str = "user",
        importance: float = 0.5,
        confidence: float = 0.5,
        authority: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> Memory:
        """Create or update a memory.  Returns the resulting ``Memory``."""
        content = self._mask(content)
        embedding = self._embed([content])[0]
        memory, _action = self._store.upsert(
            user_id=user_id,
            key=key,
            content=content,
            embedding=embedding,
            memory_type=memory_type,
            scope=scope,
            importance=importance,
            confidence=confidence,
            authority=authority,
            metadata=metadata,
        )
        return memory

    def search(
        self,
        user_id: str,
        query: str,
        *,
        top_k: int = 10,
        memory_types: list[str] | None = None,
    ) -> list[SearchResult]:
        """Semantic search over a user's memories."""
        embedding = self._embed([query])[0]
        return self._store.search(
            user_id=user_id,
            query_embedding=embedding,
            query_text=query,
            top_k=top_k,
            memory_types=memory_types,
        )

    def get(self, user_id: str, key: str) -> Memory | None:
        """Get a single memory by ``(user_id, key)``."""
        return self._store.get(user_id, key)

    def get_by_id(self, memory_id: str) -> Memory | None:
        """Get a memory by its UUID."""
        return self._store.get_by_id(memory_id)

    def list(
        self,
        user_id: str,
        *,
        memory_type: str | None = None,
        scope: str | None = None,
        status: str = "active",
        limit: int = 100,
        offset: int = 0,
    ) -> list[Memory]:
        """List memories for a user with optional filters."""
        return self._store.list(
            user_id=user_id,
            memory_type=memory_type,
            scope=scope,
            status=status,
            limit=limit,
            offset=offset,
        )

    def delete(self, user_id: str, key: str) -> bool:
        """Delete a memory.  Returns *True* if it existed."""
        return self._store.delete(user_id, key)

    def count(self, user_id: str, status: str = "active") -> int:
        """Count memories for a user."""
        return self._store.count(user_id, status)

    def versions(self, memory_id: str) -> list[MemoryVersion]:
        """Return version history for a memory (newest first)."""
        return self._store.get_versions(memory_id)

    def reset(self) -> None:
        """Delete **all** data.  Use with caution."""
        self._store.reset()

    # ── Lifecycle ───────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        self._store.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            f"agentmemodb.Client("
            f"embedding={type(self._embedding_fn).__name__}, "
            f"mask_pii={self._mask_pii})"
        )
