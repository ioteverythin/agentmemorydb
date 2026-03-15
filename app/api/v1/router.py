"""V1 API router — aggregates all sub-routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    api_keys,
    artifacts,
    bulk,
    consolidation,
    events,
    graph,
    health,
    import_export,
    masking,
    mcp,
    memories,
    memory_links,
    observations,
    projects,
    retrieval_logs,
    runs,
    scheduler,
    tasks,
    users,
    webhooks,
)

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(runs.router, prefix="/runs", tags=["runs"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
api_router.include_router(observations.router, prefix="/observations", tags=["observations"])
api_router.include_router(memories.router, prefix="/memories", tags=["memories"])
api_router.include_router(memory_links.router, prefix="/memory-links", tags=["memory-links"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(retrieval_logs.router, prefix="/retrieval-logs", tags=["retrieval-logs"])
api_router.include_router(artifacts.router, prefix="/artifacts", tags=["artifacts"])

# ── New feature routes ──────────────────────────────────────────
api_router.include_router(api_keys.router, prefix="/api-keys", tags=["auth"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(bulk.router, prefix="/bulk", tags=["bulk"])
api_router.include_router(graph.router, prefix="/graph", tags=["graph"])
api_router.include_router(consolidation.router, prefix="/consolidation", tags=["consolidation"])
api_router.include_router(import_export.router, prefix="/data", tags=["data"])
api_router.include_router(scheduler.router, prefix="/scheduler", tags=["scheduler"])
api_router.include_router(mcp.router, prefix="/mcp", tags=["mcp"])
api_router.include_router(masking.router, prefix="/masking", tags=["masking"])
