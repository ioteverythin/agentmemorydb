"""Short-term & long-term memory abstractions for agentic AI.

Provides two focused interfaces on top of the base
:class:`~agentmemodb.client.Client`:

* **ShortTermMemory** — ordered conversation buffer per thread
  (chat messages, working context, session-scoped).
* **LongTermMemory** — persistent knowledge store with semantic
  search (facts, preferences, procedures — survives across sessions).
* **MemoryManager** — combined entry-point that owns both and
  can optionally auto-promote conversation insights to long-term.

Usage::

    import agentmemodb
    from agentmemodb import MemoryManager

    mgr = MemoryManager("user-1")

    # Short-term (conversation buffer)
    mgr.short_term.add("user", "I prefer Python for backend work")
    mgr.short_term.add("assistant", "Got it — Python for backend.")
    msgs = mgr.short_term.get_messages(limit=20)

    # Long-term (persistent knowledge)
    mgr.long_term.remember("pref:language", "User prefers Python for backend")
    results = mgr.long_term.recall("What language does the user prefer?")

    # Promote a conversation insight → long-term
    mgr.promote("pref:language", "User strongly prefers Python", importance=0.9)

    mgr.close()
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from agentmemodb.client import Client
from agentmemodb.embeddings import EmbeddingFunction
from agentmemodb.types import Memory, SearchResult


# ────────────────────────────────────────────────────────────────
#  Short-term memory — conversation buffer per thread
# ────────────────────────────────────────────────────────────────


class ShortTermMemory:
    """Ordered conversation buffer tied to a thread.

    Stores messages (role + content) in an append-only sequence,
    scoped to a ``thread_id``.  Designed for chat history,
    working context, and anything that lives within a single
    session / agent run.

    Parameters
    ----------
    client : Client
        The underlying AgentMemoryDB embedded client.
    user_id : str
        Owner of the conversation.
    thread_id : str, optional
        Conversation thread identifier.  Defaults to a new UUID.
    max_messages : int, optional
        When set, ``get_messages()`` returns at most this many
        (the *latest* N).  ``None`` means unlimited.
    """

    def __init__(
        self,
        client: Client,
        user_id: str,
        thread_id: str | None = None,
        max_messages: int | None = None,
    ) -> None:
        self._client = client
        self._user_id = user_id
        self._thread_id = thread_id or str(uuid.uuid4())
        self._max_messages = max_messages

    # ── Properties ──────────────────────────────────────────────

    @property
    def thread_id(self) -> str:
        """The current thread identifier."""
        return self._thread_id

    @property
    def user_id(self) -> str:
        return self._user_id

    # ── Message operations ──────────────────────────────────────

    def add(
        self,
        role: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append a message to the conversation.

        Parameters
        ----------
        role : str
            Message role — ``"user"``, ``"assistant"``, ``"system"``,
            ``"tool"``, or any custom role.
        content : str
            The message text.
        metadata : dict, optional
            Arbitrary metadata (tool_call_id, function name, etc.).

        Returns
        -------
        dict
            The stored message with ``id``, ``seq``, ``created_at``.
        """
        return self._client._store.add_message(
            thread_id=self._thread_id,
            role=role,
            content=content,
            metadata=metadata,
        )

    def add_user(self, content: str, **kwargs: Any) -> dict[str, Any]:
        """Shortcut for ``add("user", content)``."""
        return self.add("user", content, **kwargs)

    def add_assistant(self, content: str, **kwargs: Any) -> dict[str, Any]:
        """Shortcut for ``add("assistant", content)``."""
        return self.add("assistant", content, **kwargs)

    def add_system(self, content: str, **kwargs: Any) -> dict[str, Any]:
        """Shortcut for ``add("system", content)``."""
        return self.add("system", content, **kwargs)

    def add_tool(self, content: str, **kwargs: Any) -> dict[str, Any]:
        """Shortcut for ``add("tool", content)``."""
        return self.add("tool", content, **kwargs)

    def get_messages(
        self,
        limit: int | None = None,
        *,
        roles: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve messages in chronological order.

        Parameters
        ----------
        limit : int, optional
            Max messages to return (latest N).
            Falls back to ``self.max_messages`` if not specified.
        roles : list[str], optional
            Filter by role (e.g. ``["user", "assistant"]``).
        """
        effective_limit = limit or self._max_messages
        return self._client._store.get_messages(
            thread_id=self._thread_id,
            limit=effective_limit,
            roles=roles,
        )

    def get_last(self, n: int = 1) -> list[dict[str, Any]]:
        """Return the last N messages."""
        return self.get_messages(limit=n)

    def count(self) -> int:
        """Number of messages in this thread."""
        return self._client._store.count_messages(self._thread_id)

    def clear(self) -> int:
        """Delete all messages in this thread.  Returns count deleted."""
        return self._client._store.clear_thread(self._thread_id)

    def to_list(self) -> list[dict[str, str]]:
        """Export as a simple list of ``{"role": ..., "content": ...}`` dicts.

        Compatible with OpenAI / LangChain message formats.
        """
        msgs = self.get_messages()
        return [{"role": m["role"], "content": m["content"]} for m in msgs]

    def to_string(self, separator: str = "\n") -> str:
        """Export as a formatted string (e.g. for prompt injection).

        Example output::

            user: Hello!
            assistant: Hi there!
        """
        msgs = self.get_messages()
        return separator.join(f"{m['role']}: {m['content']}" for m in msgs)

    def new_thread(self, thread_id: str | None = None) -> "ShortTermMemory":
        """Start a new conversation thread (same user, new thread_id)."""
        return ShortTermMemory(
            client=self._client,
            user_id=self._user_id,
            thread_id=thread_id,
            max_messages=self._max_messages,
        )

    def __len__(self) -> int:
        return self.count()

    def __repr__(self) -> str:
        return (
            f"ShortTermMemory(user={self._user_id!r}, "
            f"thread={self._thread_id!r}, "
            f"messages={self.count()})"
        )


# ────────────────────────────────────────────────────────────────
#  Long-term memory — persistent knowledge store
# ────────────────────────────────────────────────────────────────


class LongTermMemory:
    """Persistent, searchable knowledge store for a user.

    Wraps the base Client with domain-friendly naming and
    defaults appropriate for long-lived facts, preferences,
    and procedural knowledge.

    Parameters
    ----------
    client : Client
        The underlying AgentMemoryDB embedded client.
    user_id : str
        Owner of the memories.
    default_type : str
        Default memory type (``"semantic"``, ``"episodic"``,
        ``"procedural"``).  Defaults to ``"semantic"``.
    """

    def __init__(
        self,
        client: Client,
        user_id: str,
        default_type: str = "semantic",
    ) -> None:
        self._client = client
        self._user_id = user_id
        self._default_type = default_type

    # ── Properties ──────────────────────────────────────────────

    @property
    def user_id(self) -> str:
        return self._user_id

    # ── Knowledge operations ────────────────────────────────────

    def remember(
        self,
        key: str,
        content: str,
        *,
        memory_type: str | None = None,
        importance: float = 0.6,
        confidence: float = 0.7,
        authority: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> Memory:
        """Store or update a long-term memory.

        Parameters
        ----------
        key : str
            Unique key within this user's namespace (e.g.
            ``"pref:language"``, ``"fact:birthday"``).
        content : str
            The knowledge content.  Versioned automatically —
            if content differs from existing, a new version is
            created with the old content preserved.
        memory_type : str, optional
            ``"semantic"``, ``"episodic"``, or ``"procedural"``.
            Defaults to ``self.default_type``.
        importance : float
            How important this fact is (0–1).
        confidence : float
            How confident we are about this fact (0–1).
        metadata : dict, optional
            Arbitrary metadata (source, timestamp, tags, etc.).
        """
        return self._client.upsert(
            user_id=self._user_id,
            key=key,
            content=content,
            memory_type=memory_type or self._default_type,
            scope="user",
            importance=importance,
            confidence=confidence,
            authority=authority,
            metadata=metadata,
        )

    def recall(
        self,
        query: str,
        *,
        top_k: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[SearchResult]:
        """Semantic search over long-term memories.

        Parameters
        ----------
        query : str
            Natural language query (e.g. "What language does
            the user prefer?").
        top_k : int
            Maximum results to return.
        memory_types : list[str], optional
            Filter by type (e.g. ``["semantic", "episodic"]``).
        """
        return self._client.search(
            user_id=self._user_id,
            query=query,
            top_k=top_k,
            memory_types=memory_types,
        )

    def get(self, key: str) -> Memory | None:
        """Get a specific memory by key."""
        return self._client.get(self._user_id, key)

    def forget(self, key: str) -> bool:
        """Delete a memory.  Returns True if it existed."""
        return self._client.delete(self._user_id, key)

    def list_all(
        self,
        *,
        memory_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Memory]:
        """List all long-term memories for this user."""
        return self._client.list(
            user_id=self._user_id,
            memory_type=memory_type,
            scope="user",
            limit=limit,
            offset=offset,
        )

    def count(self) -> int:
        """Count active long-term memories."""
        return self._client.count(self._user_id)

    def __repr__(self) -> str:
        return (
            f"LongTermMemory(user={self._user_id!r}, "
            f"type={self._default_type!r}, "
            f"count={self.count()})"
        )


# ────────────────────────────────────────────────────────────────
#  MemoryManager — unified interface
# ────────────────────────────────────────────────────────────────


class MemoryManager:
    """Unified memory manager combining short-term and long-term.

    Provides a single entry-point for agents that need both
    conversation history and persistent knowledge.

    Parameters
    ----------
    user_id : str
        The agent / user identity.
    path : str, optional
        SQLite database path (same as ``Client(path=...)``).
    embedding_fn : EmbeddingFunction, optional
        Embedding function for long-term semantic search.
    mask_pii : bool
        Enable PII masking on long-term memories.
    thread_id : str, optional
        Initial conversation thread.  Auto-generated if not set.
    max_messages : int, optional
        Cap on conversation buffer size (latest N).

    Usage::

        from agentmemodb import MemoryManager

        mgr = MemoryManager("agent-1")

        # Conversation
        mgr.short_term.add_user("I love Python!")
        mgr.short_term.add_assistant("Noted, Python it is.")

        # Knowledge
        mgr.long_term.remember("pref:lang", "User loves Python")
        results = mgr.long_term.recall("programming language?")

        # Promote insight from conversation → long-term
        mgr.promote("pref:lang", "User strongly prefers Python",
                     importance=0.9)

        # Switch conversation thread
        mgr.new_thread("session-2")
        mgr.short_term.add_user("Starting a new task...")

        mgr.close()
    """

    def __init__(
        self,
        user_id: str,
        *,
        path: str | None = None,
        embedding_fn: EmbeddingFunction | None = None,
        mask_pii: bool = False,
        thread_id: str | None = None,
        max_messages: int | None = None,
    ) -> None:
        self._user_id = user_id
        self._client = Client(
            path=path,
            embedding_fn=embedding_fn,
            mask_pii=mask_pii,
        )
        self._short_term = ShortTermMemory(
            client=self._client,
            user_id=user_id,
            thread_id=thread_id,
            max_messages=max_messages,
        )
        self._long_term = LongTermMemory(
            client=self._client,
            user_id=user_id,
        )

    # ── Properties ──────────────────────────────────────────────

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def short_term(self) -> ShortTermMemory:
        """Access the short-term (conversation) memory."""
        return self._short_term

    @property
    def long_term(self) -> LongTermMemory:
        """Access the long-term (knowledge) memory."""
        return self._long_term

    @property
    def client(self) -> Client:
        """Access the underlying Client directly."""
        return self._client

    # ── Convenience methods ─────────────────────────────────────

    def promote(
        self,
        key: str,
        content: str,
        *,
        memory_type: str = "semantic",
        importance: float = 0.7,
        confidence: float = 0.8,
        metadata: dict[str, Any] | None = None,
    ) -> Memory:
        """Promote a conversation insight to long-term memory.

        Use this when the agent identifies something worth
        remembering permanently from the current conversation.
        """
        meta = metadata or {}
        meta.setdefault("source", "conversation")
        meta.setdefault("thread_id", self._short_term.thread_id)
        meta.setdefault("promoted_at", datetime.now(timezone.utc).isoformat())
        return self._long_term.remember(
            key,
            content,
            memory_type=memory_type,
            importance=importance,
            confidence=confidence,
            metadata=meta,
        )

    def new_thread(self, thread_id: str | None = None) -> ShortTermMemory:
        """Start a new conversation thread.

        Updates ``self.short_term`` to point to the new thread
        and returns it.
        """
        self._short_term = self._short_term.new_thread(thread_id)
        return self._short_term

    def get_context_window(
        self,
        query: str | None = None,
        *,
        n_messages: int = 10,
        n_memories: int = 5,
    ) -> dict[str, Any]:
        """Build a combined context window for LLM prompting.

        Returns a dict with:
        - ``messages`` — latest N conversation messages
        - ``relevant_memories`` — top-K long-term memories
          (only if *query* is provided)
        - ``stats`` — message count + memory count

        This is the typical input you'd inject into an LLM prompt
        or a LangChain/LangGraph node.
        """
        messages = self._short_term.get_messages(limit=n_messages)
        relevant: list[dict[str, Any]] = []

        if query:
            results = self._long_term.recall(query, top_k=n_memories)
            relevant = [
                {
                    "key": r.key,
                    "content": r.content,
                    "score": round(r.score, 4),
                    "type": r.memory.memory_type,
                }
                for r in results
            ]

        return {
            "messages": messages,
            "relevant_memories": relevant,
            "stats": {
                "thread_id": self._short_term.thread_id,
                "message_count": self._short_term.count(),
                "memory_count": self._long_term.count(),
            },
        }

    def reset(self) -> None:
        """Clear ALL data (both short-term and long-term).  Use with caution."""
        self._short_term.clear()
        self._client.reset()

    # ── Lifecycle ───────────────────────────────────────────────

    def close(self) -> None:
        """Release database resources."""
        self._client.close()

    def __enter__(self) -> "MemoryManager":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            f"MemoryManager(user={self._user_id!r}, "
            f"thread={self._short_term.thread_id!r}, "
            f"messages={self._short_term.count()}, "
            f"memories={self._long_term.count()})"
        )
