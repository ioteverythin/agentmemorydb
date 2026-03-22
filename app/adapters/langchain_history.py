"""LangChain ChatMessageHistory adapter backed by AgentMemoryDB.

Gives LangChain / LCEL users a drop-in history store backed by
AgentMemoryDB's auditable, searchable episodic memory.

Usage::

    from app.adapters.langchain_history import AgentMemoryDBChatMessageHistory

    history = AgentMemoryDBChatMessageHistory(
        base_url="http://localhost:8100",
        user_id="alice-uuid",
        session_id="session-001",
        message_ttl_seconds=7 * 24 * 3600,
    )

    # Add messages
    await history.aadd_messages([HumanMessage(content="Hello!")])

    # Retrieve
    msgs = await history.aget_messages()

    # Use with LangChain LCEL
    from langchain_core.runnables.history import RunnableWithMessageHistory
    chain_with_history = RunnableWithMessageHistory(chain, lambda sid: history)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

try:
    from langchain_core.chat_history import BaseChatMessageHistory
    from langchain_core.messages import (
        AIMessage,
        BaseMessage,
        HumanMessage,
        SystemMessage,
    )
except ImportError as exc:
    raise ImportError(
        "langchain-core is required for the ChatMessageHistory adapter. "
        "Install with: pip install langchain-core"
    ) from exc


_ROLE_MAP: dict[str, type[BaseMessage]] = {
    "human": HumanMessage,
    "ai": AIMessage,
    "system": SystemMessage,
}


class AgentMemoryDBChatMessageHistory(BaseChatMessageHistory):
    """LangChain ``BaseChatMessageHistory`` backed by AgentMemoryDB.

    Each message is stored as an ``episodic`` memory with
    ``memory_key = {session_id}:{sequence_number}``.

    Uses ``archived`` status instead of hard-delete to preserve the
    audit trail when ``clear()`` is called.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:8100",
        user_id: str,
        session_id: str,
        message_ttl_seconds: int | None = None,
        scope: str = "user",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.session_id = session_id
        self.message_ttl_seconds = message_ttl_seconds
        self.scope = scope
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30)
        self._seq = 0  # monotonic counter within session

    # ── Read ────────────────────────────────────────────────────

    @property
    def messages(self) -> list[BaseMessage]:
        """Synchronous access — not supported by the async adapter."""
        raise NotImplementedError(
            "AgentMemoryDBChatMessageHistory is async-only. Use aget_messages()."
        )

    async def aget_messages(self) -> list[BaseMessage]:
        """Retrieve all messages for this session, ordered chronologically."""
        resp = await self._client.get(
            "/api/v1/memories",
            params={
                "user_id": self.user_id,
                "memory_type": "episodic",
                "scope": self.scope,
                "status": "active",
                "limit": 1000,
            },
        )
        resp.raise_for_status()
        memories = resp.json()

        # Filter to this session and sort by memory_key (session:seq)
        session_memories = [
            m for m in memories if m["memory_key"].startswith(f"{self.session_id}:")
        ]
        session_memories.sort(key=lambda m: m["memory_key"])

        result: list[BaseMessage] = []
        for mem in session_memories:
            payload = mem.get("payload") or {}
            role = payload.get("role", "human")
            cls = _ROLE_MAP.get(role, HumanMessage)
            result.append(cls(content=mem["content"]))

        return result

    # ── Write ───────────────────────────────────────────────────

    async def aadd_messages(self, messages: list[BaseMessage]) -> None:
        """Persist messages as episodic memories."""
        for msg in messages:
            self._seq += 1
            role = _classify_role(msg)
            memory_key = f"{self.session_id}:{self._seq:06d}"

            body: dict[str, Any] = {
                "user_id": self.user_id,
                "memory_key": memory_key,
                "memory_type": "episodic",
                "scope": self.scope,
                "content": msg.content,
                "source_type": "user_input" if role == "human" else "tool_output",
                "payload": {"role": role, "session_id": self.session_id},
                "confidence": 1.0,
            }

            if self.message_ttl_seconds is not None:
                body["expires_at"] = (
                    datetime.now(UTC) + timedelta(seconds=self.message_ttl_seconds)
                ).isoformat()

            resp = await self._client.post("/api/v1/memories/upsert", json=body)
            resp.raise_for_status()

    def add_message(self, message: BaseMessage) -> None:
        """Synchronous fallback — not supported."""
        raise NotImplementedError(
            "AgentMemoryDBChatMessageHistory is async-only. Use aadd_messages()."
        )

    # ── Clear ───────────────────────────────────────────────────

    async def aclear(self) -> None:
        """Archive (soft-delete) all messages in this session.

        Uses ``archived`` status instead of hard-delete so the audit
        trail is preserved.
        """
        resp = await self._client.get(
            "/api/v1/memories",
            params={
                "user_id": self.user_id,
                "memory_type": "episodic",
                "scope": self.scope,
                "status": "active",
                "limit": 1000,
            },
        )
        resp.raise_for_status()
        memories = resp.json()

        for mem in memories:
            if mem["memory_key"].startswith(f"{self.session_id}:"):
                await self._client.patch(
                    f"/api/v1/memories/{mem['id']}/status",
                    json={"status": "archived"},
                )

    def clear(self) -> None:
        """Synchronous fallback — not supported."""
        raise NotImplementedError("AgentMemoryDBChatMessageHistory is async-only. Use aclear().")

    # ── Lifecycle ───────────────────────────────────────────────

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


def _classify_role(msg: BaseMessage) -> str:
    """Map a LangChain message to a role string."""
    if isinstance(msg, HumanMessage):
        return "human"
    if isinstance(msg, AIMessage):
        return "ai"
    if isinstance(msg, SystemMessage):
        return "system"
    return "human"
