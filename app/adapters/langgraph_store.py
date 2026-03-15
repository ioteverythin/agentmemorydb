"""LangGraph adapter stub — shows how to plug AgentMemoryDB into LangGraph.

This is a placeholder that demonstrates the interface.
A production implementation would subclass LangGraph's ``BaseStore``
(or ``BaseCheckpointSaver``) and delegate to AgentMemoryDB's HTTP API
or service layer.

Usage concept (LangGraph side):

    from agentmemorydb.adapters.langgraph_store import AgentMemoryDBStore

    store = AgentMemoryDBStore(base_url="http://localhost:8100")
    graph = StateGraph(..., store=store)

References:
    - LangGraph BaseStore: langgraph.store.base.BaseStore
    - LangGraph PostgresSaver: langgraph.checkpoint.postgres
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx


class AgentMemoryDBStore:
    """Adapter that wraps AgentMemoryDB's REST API for use as a LangGraph store.

    This is a **stub** — it sketches the interface but is not yet a full
    BaseStore implementation.  It can be used today to read/write memories
    from agent code that runs inside a LangGraph graph.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8100",
        user_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._user_id = user_id
        self._project_id = project_id
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=30.0)

    # ── Write ───────────────────────────────────────────────────

    async def put(
        self,
        key: str,
        value: str,
        *,
        memory_type: str = "semantic",
        scope: str = "user",
        **kwargs: Any,
    ) -> dict:
        """Upsert a memory via the AgentMemoryDB API."""
        payload = {
            "user_id": self._user_id,
            "project_id": self._project_id,
            "memory_key": key,
            "memory_type": memory_type,
            "scope": scope,
            "content": value,
            **kwargs,
        }
        resp = await self._client.post("/api/v1/memories/upsert", json=payload)
        resp.raise_for_status()
        return resp.json()

    # ── Read ────────────────────────────────────────────────────

    async def search(
        self,
        query: str | None = None,
        *,
        top_k: int = 5,
        memory_types: list[str] | None = None,
        **kwargs: Any,
    ) -> list[dict]:
        """Search memories via the AgentMemoryDB API."""
        payload: dict[str, Any] = {
            "user_id": self._user_id,
            "query_text": query,
            "top_k": top_k,
            "explain": True,
        }
        if self._project_id:
            payload["project_id"] = self._project_id
        if memory_types:
            payload["memory_types"] = memory_types
        payload.update(kwargs)
        resp = await self._client.post("/api/v1/memories/search", json=payload)
        resp.raise_for_status()
        return resp.json().get("results", [])

    async def get(self, memory_id: str) -> dict:
        """Get a single memory by ID."""
        resp = await self._client.get(f"/api/v1/memories/{memory_id}")
        resp.raise_for_status()
        return resp.json()

    # ── Lifecycle ───────────────────────────────────────────────

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AgentMemoryDBStore":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
