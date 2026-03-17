"""AgentMemoryDB Python SDK — typed async client for all API operations.

Usage:
    from app.sdk.client import AgentMemoryDBClient

    async with AgentMemoryDBClient("http://localhost:8100") as client:
        user = await client.create_user("alice")
        memory = await client.upsert_memory(
            user_id=user["id"],
            memory_key="pref:color",
            content="User prefers blue.",
        )
        results = await client.search_memories(
            user_id=user["id"],
            query="What colour?",
        )
"""

from __future__ import annotations

from typing import Any

import httpx


class AgentMemoryDBError(Exception):
    """Raised when the AgentMemoryDB API returns an error."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class AgentMemoryDBClient:
    """Typed async Python client for AgentMemoryDB.

    Provides methods for all major API operations with proper
    error handling and type hints.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8100",
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        headers: dict[str, str] = {}
        if api_key:
            headers["X-API-Key"] = api_key

        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers=headers,
        )

    # ── Lifecycle ───────────────────────────────────────────────

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AgentMemoryDBClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ── Internal ────────────────────────────────────────────────

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise AgentMemoryDBError(resp.status_code, str(detail))

    # ── Health ──────────────────────────────────────────────────

    async def health(self) -> dict:
        resp = await self._client.get("/api/v1/health")
        self._raise_for_status(resp)
        return resp.json()

    async def version(self) -> dict:
        resp = await self._client.get("/api/v1/version")
        self._raise_for_status(resp)
        return resp.json()

    # ── Users ───────────────────────────────────────────────────

    async def create_user(self, name: str, **kwargs: Any) -> dict:
        resp = await self._client.post("/api/v1/users", json={"name": name, **kwargs})
        self._raise_for_status(resp)
        return resp.json()

    # ── Projects ────────────────────────────────────────────────

    async def create_project(self, user_id: str, name: str, description: str | None = None) -> dict:
        payload: dict[str, Any] = {"user_id": user_id, "name": name}
        if description:
            payload["description"] = description
        resp = await self._client.post("/api/v1/projects", json=payload)
        self._raise_for_status(resp)
        return resp.json()

    # ── Runs ────────────────────────────────────────────────────

    async def create_run(
        self,
        user_id: str,
        agent_name: str,
        *,
        project_id: str | None = None,
        status: str = "running",
    ) -> dict:
        payload: dict[str, Any] = {
            "user_id": user_id,
            "agent_name": agent_name,
            "status": status,
        }
        if project_id:
            payload["project_id"] = project_id
        resp = await self._client.post("/api/v1/runs", json=payload)
        self._raise_for_status(resp)
        return resp.json()

    async def complete_run(self, run_id: str, summary: str | None = None) -> dict:
        payload: dict[str, Any] = {}
        if summary:
            payload["summary"] = summary
        resp = await self._client.patch(f"/api/v1/runs/{run_id}/complete", json=payload)
        self._raise_for_status(resp)
        return resp.json()

    # ── Events ──────────────────────────────────────────────────

    async def create_event(
        self,
        run_id: str,
        user_id: str,
        event_type: str,
        content: str,
        *,
        source: str | None = None,
        payload: dict | None = None,
    ) -> dict:
        body: dict[str, Any] = {
            "run_id": run_id,
            "user_id": user_id,
            "event_type": event_type,
            "content": content,
        }
        if source:
            body["source"] = source
        if payload:
            body["payload"] = payload
        resp = await self._client.post("/api/v1/events", json=body)
        self._raise_for_status(resp)
        return resp.json()

    # ── Observations ────────────────────────────────────────────

    async def extract_observations(self, event_id: str) -> list[dict]:
        resp = await self._client.post(
            "/api/v1/observations/extract-from-event",
            json={"event_id": event_id},
        )
        self._raise_for_status(resp)
        return resp.json()

    # ── Memories ────────────────────────────────────────────────

    async def upsert_memory(
        self,
        user_id: str,
        memory_key: str,
        content: str,
        *,
        memory_type: str = "semantic",
        scope: str = "user",
        importance_score: float = 0.5,
        confidence: float = 0.5,
        is_contradiction: bool = False,
        **kwargs: Any,
    ) -> dict:
        payload: dict[str, Any] = {
            "user_id": user_id,
            "memory_key": memory_key,
            "content": content,
            "memory_type": memory_type,
            "scope": scope,
            "importance_score": importance_score,
            "confidence": confidence,
            "is_contradiction": is_contradiction,
            **kwargs,
        }
        resp = await self._client.post("/api/v1/memories/upsert", json=payload)
        self._raise_for_status(resp)
        return resp.json()

    async def get_memory(self, memory_id: str) -> dict:
        resp = await self._client.get(f"/api/v1/memories/{memory_id}")
        self._raise_for_status(resp)
        return resp.json()

    async def search_memories(
        self,
        user_id: str,
        query: str,
        *,
        top_k: int = 10,
        explain: bool = True,
        memory_types: list[str] | None = None,
        scopes: list[str] | None = None,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> dict:
        payload: dict[str, Any] = {
            "user_id": user_id,
            "query_text": query,
            "top_k": top_k,
            "explain": explain,
            **kwargs,
        }
        if memory_types:
            payload["memory_types"] = memory_types
        if scopes:
            payload["scopes"] = scopes
        if run_id:
            payload["run_id"] = run_id
        resp = await self._client.post("/api/v1/memories/search", json=payload)
        self._raise_for_status(resp)
        return resp.json()

    async def list_memories(
        self,
        user_id: str,
        *,
        memory_type: str | None = None,
        scope: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        params: dict[str, Any] = {"user_id": user_id, "limit": limit, "offset": offset}
        if memory_type:
            params["memory_type"] = memory_type
        if scope:
            params["scope"] = scope
        if status:
            params["status"] = status
        resp = await self._client.get("/api/v1/memories", params=params)
        self._raise_for_status(resp)
        return resp.json()

    async def update_memory_status(self, memory_id: str, status: str) -> dict:
        resp = await self._client.patch(
            f"/api/v1/memories/{memory_id}/status", json={"status": status}
        )
        self._raise_for_status(resp)
        return resp.json()

    async def get_memory_versions(self, memory_id: str) -> list[dict]:
        resp = await self._client.get(f"/api/v1/memories/{memory_id}/versions")
        self._raise_for_status(resp)
        return resp.json()

    async def get_memory_links(self, memory_id: str) -> list[dict]:
        resp = await self._client.get(f"/api/v1/memories/{memory_id}/links")
        self._raise_for_status(resp)
        return resp.json()

    # ── Bulk Operations ─────────────────────────────────────────

    async def batch_upsert(self, memories: list[dict]) -> dict:
        resp = await self._client.post("/api/v1/bulk/upsert", json={"memories": memories})
        self._raise_for_status(resp)
        return resp.json()

    async def batch_search(self, queries: list[dict]) -> dict:
        resp = await self._client.post("/api/v1/bulk/search", json={"queries": queries})
        self._raise_for_status(resp)
        return resp.json()

    # ── Graph ───────────────────────────────────────────────────

    async def expand_graph(
        self,
        seed_memory_id: str,
        *,
        max_hops: int = 2,
        link_types: list[str] | None = None,
        max_nodes: int = 50,
    ) -> dict:
        payload: dict[str, Any] = {
            "seed_memory_id": seed_memory_id,
            "max_hops": max_hops,
            "max_nodes": max_nodes,
        }
        if link_types:
            payload["link_types"] = link_types
        resp = await self._client.post("/api/v1/graph/expand", json=payload)
        self._raise_for_status(resp)
        return resp.json()

    async def shortest_path(self, source_id: str, target_id: str, max_depth: int = 5) -> dict:
        resp = await self._client.post(
            "/api/v1/graph/shortest-path",
            json={
                "source_id": source_id,
                "target_id": target_id,
                "max_depth": max_depth,
            },
        )
        self._raise_for_status(resp)
        return resp.json()

    # ── Tasks ───────────────────────────────────────────────────

    async def create_task(
        self,
        user_id: str,
        title: str,
        *,
        run_id: str | None = None,
        description: str | None = None,
        priority: int = 0,
    ) -> dict:
        payload: dict[str, Any] = {"user_id": user_id, "title": title, "priority": priority}
        if run_id:
            payload["run_id"] = run_id
        if description:
            payload["description"] = description
        resp = await self._client.post("/api/v1/tasks", json=payload)
        self._raise_for_status(resp)
        return resp.json()

    async def transition_task(
        self,
        task_id: str,
        to_state: str,
        *,
        reason: str | None = None,
        triggered_by: str | None = None,
    ) -> dict:
        payload: dict[str, Any] = {"to_state": to_state}
        if reason:
            payload["reason"] = reason
        if triggered_by:
            payload["triggered_by"] = triggered_by
        resp = await self._client.patch(f"/api/v1/tasks/{task_id}/transition", json=payload)
        self._raise_for_status(resp)
        return resp.json()

    # ── Import / Export ─────────────────────────────────────────

    async def export_memories(
        self, user_id: str, *, include_versions: bool = True, include_links: bool = True
    ) -> dict:
        resp = await self._client.get(
            "/api/v1/data/export",
            params={
                "user_id": user_id,
                "include_versions": include_versions,
                "include_links": include_links,
            },
        )
        self._raise_for_status(resp)
        return resp.json()

    async def import_memories(self, user_id: str, data: dict, *, strategy: str = "upsert") -> dict:
        resp = await self._client.post(
            "/api/v1/data/import",
            json={"user_id": user_id, "data": data, "strategy": strategy},
        )
        self._raise_for_status(resp)
        return resp.json()

    # ── Webhooks ────────────────────────────────────────────────

    async def register_webhook(
        self, user_id: str, url: str, *, events: str = "*", secret: str | None = None
    ) -> dict:
        payload: dict[str, Any] = {"user_id": user_id, "url": url, "events": events}
        if secret:
            payload["secret"] = secret
        resp = await self._client.post("/api/v1/webhooks", json=payload)
        self._raise_for_status(resp)
        return resp.json()

    async def list_webhooks(self, user_id: str) -> list[dict]:
        resp = await self._client.get("/api/v1/webhooks", params={"user_id": user_id})
        self._raise_for_status(resp)
        return resp.json()

    # ── Consolidation ───────────────────────────────────────────

    async def find_duplicates(self, user_id: str) -> list[dict]:
        resp = await self._client.get(
            "/api/v1/consolidation/duplicates", params={"user_id": user_id}
        )
        self._raise_for_status(resp)
        return resp.json()

    async def auto_consolidate(self, user_id: str) -> dict:
        resp = await self._client.post("/api/v1/consolidation/auto", params={"user_id": user_id})
        self._raise_for_status(resp)
        return resp.json()
