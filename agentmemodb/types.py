"""Data types for the AgentMemoryDB pip package.

Lightweight dataclasses — no Pydantic or server dependencies required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Memory:
    """A single memory unit.

    Mirrors the server's Memory model but as a plain dataclass
    so the embedded client has zero heavy dependencies.
    """

    id: str
    user_id: str
    key: str
    content: str
    memory_type: str = "semantic"
    scope: str = "user"
    status: str = "active"
    importance: float = 0.5
    confidence: float = 0.5
    authority: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    content_hash: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "memory_key": self.key,
            "content": self.content,
            "memory_type": self.memory_type,
            "scope": self.scope,
            "status": self.status,
            "importance_score": self.importance,
            "confidence": self.confidence,
            "authority_level": self.authority,
            "payload": self.metadata,
            "version": self.version,
            "content_hash": self.content_hash,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class SearchResult:
    """A memory paired with its similarity / relevance score."""

    memory: Memory
    score: float = 0.0

    # ── Convenience accessors ──

    @property
    def key(self) -> str:
        return self.memory.key

    @property
    def content(self) -> str:
        return self.memory.content

    @property
    def id(self) -> str:
        return self.memory.id


@dataclass
class MemoryVersion:
    """Historical snapshot of a memory's content at a given version."""

    id: str
    memory_id: str
    version: int
    content: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
