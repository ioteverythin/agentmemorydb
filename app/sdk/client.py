"""EngramDB Python SDK — typed async client for all API operations.

Usage:
    from app.sdk.client import EngramDBClient

    async with EngramDBClient("http://localhost:8100") as client:
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

from datetime import datetime
from typing import Any

import httpx


def _iso(value: str | datetime) -> str:
    """Normalise a timestamp argument to ISO-8601 for the wire."""
    return value.isoformat() if isinstance(value, datetime) else value


class EngramDBError(Exception):
    """Raised when the EngramDB API returns an error."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class EngramDBClient:
    """Typed async Python client for EngramDB.

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

    async def __aenter__(self) -> EngramDBClient:
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
            raise EngramDBError(resp.status_code, str(detail))

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
        pinned: bool | None = None,
        origin: str | None = None,
        origin_ref: str | None = None,
        **kwargs: Any,
    ) -> dict:
        """Create or update a memory.

        ``origin`` declares the trust domain of the writer (``user``,
        ``operator``, ``agent_inference``, ``tool_output``, ``external_ingest``,
        …). It caps the authority this write may claim and decides whether an
        untrusted, low-confidence write is quarantined — so attribute honestly.
        """
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
        if pinned is not None:
            payload["pinned"] = pinned
        if origin is not None:
            payload["origin"] = origin
        if origin_ref is not None:
            payload["origin_ref"] = origin_ref
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
        as_of: str | datetime | None = None,
        **kwargs: Any,
    ) -> dict:
        """Hybrid search. Pass ``as_of`` to search the facts valid at an instant."""
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
        if as_of is not None:
            payload["as_of"] = _iso(as_of)
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
        as_of: str | datetime | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {"user_id": user_id, "limit": limit, "offset": offset}
        if memory_type:
            params["memory_type"] = memory_type
        if scope:
            params["scope"] = scope
        if status:
            params["status"] = status
        if as_of is not None:
            params["as_of"] = _iso(as_of)
        resp = await self._client.get("/api/v1/memories", params=params)
        self._raise_for_status(resp)
        return resp.json()

    async def update_memory_status(self, memory_id: str, status: str) -> dict:
        resp = await self._client.patch(
            f"/api/v1/memories/{memory_id}/status", json={"status": status}
        )
        self._raise_for_status(resp)
        return resp.json()

    async def timeline(self, memory_id: str) -> dict:
        """The full supersession chain for a memory, oldest generation first."""
        resp = await self._client.get(f"/api/v1/memories/{memory_id}/timeline")
        self._raise_for_status(resp)
        return resp.json()

    async def invalidate_memory(
        self, memory_id: str, *, valid_to: str | datetime | None = None
    ) -> dict:
        """Close a fact's validity window with no replacement (it stopped being true)."""
        payload: dict[str, Any] = {}
        if valid_to is not None:
            payload["valid_to"] = _iso(valid_to)
        resp = await self._client.post(f"/api/v1/memories/{memory_id}/invalidate", json=payload)
        self._raise_for_status(resp)
        return resp.json()

    # ── Forgetting ──────────────────────────────────────────────

    async def pin_memory(self, memory_id: str, *, pinned: bool = True) -> dict:
        """Pin (or unpin) a memory so it is never decayed or auto-archived."""
        resp = await self._client.patch(
            f"/api/v1/memories/{memory_id}/pin", json={"pinned": pinned}
        )
        self._raise_for_status(resp)
        return resp.json()

    async def erase(self, memory_id: str, *, reason: str | None = None) -> dict:
        """Hard-erase a memory (irreversible; needs an API key with ``erase`` scope).

        A ``forgetting_log`` tombstone with the content's SHA-256 survives, so the
        erasure is auditable without the content.
        """
        params: dict[str, Any] = {"mode": "erase"}
        if reason:
            params["reason"] = reason
        resp = await self._client.delete(f"/api/v1/memories/{memory_id}", params=params)
        self._raise_for_status(resp)
        return resp.json()

    async def erase_user(self, user_id: str, *, reason: str | None = None) -> dict:
        """Erase every memory for a user (GDPR right-to-be-forgotten)."""
        params: dict[str, Any] = {"mode": "erase"}
        if reason:
            params["reason"] = reason
        resp = await self._client.delete(f"/api/v1/users/{user_id}/memories", params=params)
        self._raise_for_status(resp)
        return resp.json()

    # ── Automatic memory linking ────────────────────────────────

    async def autolink_memory(self, memory_id: str) -> list[dict]:
        """Link a memory to its nearest topical neighbours now.

        Runs on request whether or not ``ENABLE_AUTOLINK`` is on, and is safe to
        call twice — edges are deduplicated in both directions.
        """
        resp = await self._client.post(f"/api/v1/memories/{memory_id}/autolink")
        self._raise_for_status(resp)
        return resp.json()

    async def autolink_backfill(
        self, user_id: str, *, limit: int = 500, dry_run: bool = True
    ) -> dict:
        """Autolink a user's existing memories (dry run by default)."""
        resp = await self._client.post(
            "/api/v1/graph/autolink-backfill",
            params={"user_id": user_id, "limit": limit, "dry_run": dry_run},
        )
        self._raise_for_status(resp)
        return resp.json()

    # ── Reflection (sleep-time consolidation) ───────────────────

    async def reflect(
        self, user_id: str, *, project_id: str | None = None, dry_run: bool = False
    ) -> dict:
        """Run a reflection pass for a user.

        Returns the run record whether or not it produced insights — a skip is a
        result, and ``skipped_reason`` says which one (notably
        ``no_llm_provider``, which means the feature is on but has no model).
        """
        params: dict[str, Any] = {"user_id": user_id, "dry_run": dry_run}
        if project_id:
            params["project_id"] = project_id
        resp = await self._client.post("/api/v1/consolidation/reflect", params=params)
        self._raise_for_status(resp)
        return resp.json()

    async def consolidation_runs(
        self, *, user_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        """Reflection pass history, newest first."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if user_id:
            params["user_id"] = user_id
        resp = await self._client.get("/api/v1/consolidation/runs", params=params)
        self._raise_for_status(resp)
        return resp.json()

    # ── Provenance ──────────────────────────────────────────────

    async def origin_policy(self) -> dict:
        """The active trust policy: authority ceilings and quarantine rules."""
        resp = await self._client.get("/api/v1/provenance/policy")
        self._raise_for_status(resp)
        return resp.json()

    async def list_quarantined(
        self, *, user_id: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[dict]:
        """The review queue — writes held back because their origin was untrusted."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if user_id:
            params["user_id"] = user_id
        resp = await self._client.get("/api/v1/provenance/quarantine", params=params)
        self._raise_for_status(resp)
        return resp.json()

    async def review_quarantined(
        self, memory_id: str, *, approve: bool, reviewer: str | None = None
    ) -> dict:
        """Approve a quarantined memory into active recall, or reject it."""
        resp = await self._client.post(
            f"/api/v1/provenance/quarantine/{memory_id}/review",
            json={"approve": approve, "reviewer": reviewer},
        )
        self._raise_for_status(resp)
        return resp.json()

    async def forgetting_log(
        self, *, user_id: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[dict]:
        """Read the forgetting audit trail — decay, expiry, and erasure decisions."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if user_id:
            params["user_id"] = user_id
        resp = await self._client.get("/api/v1/forgetting/log", params=params)
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
