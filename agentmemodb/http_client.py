"""Remote AgentMemoryDB client — connects to a running server over HTTP.

Usage::

    import agentmemodb

    db = agentmemodb.HttpClient("http://localhost:8100")
    db = agentmemodb.HttpClient("http://localhost:8100", api_key="amdb_...")

    db.upsert("user-1", "pref:lang", "User prefers Python")
    results = db.search("user-1", "language?")
    db.close()

Provides the **same API surface** as :class:`agentmemodb.Client` so
you can swap between embedded and remote mode without changing code.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from agentmemodb.types import Memory, SearchResult


class HttpClient:
    """Synchronous HTTP client for a remote AgentMemoryDB server.

    Parameters
    ----------
    url
        Base URL of the AgentMemoryDB server (e.g. ``http://localhost:8100``).
    api_key
        Optional API key sent via ``X-API-Key`` header.
    timeout
        HTTP request timeout in seconds.
    """

    def __init__(
        self,
        url: str = "http://localhost:8100",
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        headers: dict[str, str] = {}
        if api_key:
            headers["X-API-Key"] = api_key

        self._client = httpx.Client(
            base_url=url.rstrip("/"),
            timeout=timeout,
            headers=headers,
        )

    # ── Internal helpers ────────────────────────────────────────

    def _raise(self, resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise RuntimeError(
                f"AgentMemoryDB HTTP {resp.status_code}: {detail}"
            )

    @staticmethod
    def _dict_to_memory(d: dict[str, Any]) -> Memory:
        return Memory(
            id=d.get("id", ""),
            user_id=d.get("user_id", ""),
            key=d.get("memory_key", ""),
            content=d.get("content", ""),
            memory_type=d.get("memory_type", "semantic"),
            scope=d.get("scope", "user"),
            status=d.get("status", "active"),
            importance=d.get("importance_score", 0.5),
            confidence=d.get("confidence", 0.5),
            authority=d.get("authority_level", 0.0),
            metadata=d.get("payload") or {},
            version=d.get("version", 1),
            content_hash=d.get("content_hash", ""),
            created_at=(
                datetime.fromisoformat(d["created_at"])
                if d.get("created_at")
                else datetime.now(timezone.utc)
            ),
            updated_at=(
                datetime.fromisoformat(d["updated_at"])
                if d.get("updated_at")
                else datetime.now(timezone.utc)
            ),
        )

    # ── Core API (mirrors Client) ───────────────────────────────

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
        """Create or update a memory on the remote server."""
        resp = self._client.post(
            "/api/v1/memories/upsert",
            json={
                "user_id": user_id,
                "memory_key": key,
                "content": content,
                "memory_type": memory_type,
                "scope": scope,
                "importance_score": importance,
                "confidence": confidence,
                "authority_level": authority,
                "payload": metadata,
            },
        )
        self._raise(resp)
        return self._dict_to_memory(resp.json())

    def search(
        self,
        user_id: str,
        query: str,
        *,
        top_k: int = 10,
        memory_types: list[str] | None = None,
    ) -> list[SearchResult]:
        """Hybrid search on the remote server."""
        payload: dict[str, Any] = {
            "user_id": user_id,
            "query_text": query,
            "top_k": top_k,
        }
        if memory_types:
            payload["memory_types"] = memory_types

        resp = self._client.post("/api/v1/memories/search", json=payload)
        self._raise(resp)
        data = resp.json()

        items = data.get("results", data if isinstance(data, list) else [])
        results: list[SearchResult] = []
        for item in items:
            mem_data = item.get("memory", item)
            memory = self._dict_to_memory(mem_data)
            score = item.get("final_score", item.get("score", 0.0))
            results.append(SearchResult(memory=memory, score=score))
        return results

    def get(self, user_id: str, key: str) -> Memory | None:
        """Get a memory by ``(user_id, key)``."""
        resp = self._client.get(
            "/api/v1/memories",
            params={"user_id": user_id, "memory_key": key, "limit": 1},
        )
        self._raise(resp)
        items = resp.json()
        if not items:
            return None
        return self._dict_to_memory(items[0])

    def get_by_id(self, memory_id: str) -> Memory | None:
        """Get a memory by UUID."""
        resp = self._client.get(f"/api/v1/memories/{memory_id}")
        if resp.status_code == 404:
            return None
        self._raise(resp)
        return self._dict_to_memory(resp.json())

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
        """List memories with optional filters."""
        params: dict[str, Any] = {
            "user_id": user_id,
            "status": status,
            "limit": limit,
            "offset": offset,
        }
        if memory_type:
            params["memory_type"] = memory_type
        if scope:
            params["scope"] = scope

        resp = self._client.get("/api/v1/memories", params=params)
        self._raise(resp)
        return [self._dict_to_memory(d) for d in resp.json()]

    def delete(self, user_id: str, key: str) -> bool:
        """Retract a memory (status → retracted). Returns *True* if found."""
        mem = self.get(user_id, key)
        if not mem:
            return False
        resp = self._client.patch(
            f"/api/v1/memories/{mem.id}/status",
            json={"status": "retracted"},
        )
        return resp.status_code < 400

    def count(self, user_id: str, status: str = "active") -> int:
        """Count memories (fetches the list, then counts)."""
        return len(self.list(user_id, status=status, limit=10_000))

    # ── Lifecycle ───────────────────────────────────────────────

    def close(self) -> None:
        """Close the HTTP transport."""
        self._client.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"agentmemodb.HttpClient(url={self._client.base_url!r})"
