"""Prometheus metrics for AgentMemoryDB.

Exposes /metrics endpoint and provides request instrumentation.
Uses the lightweight `prometheus_client` library.
"""

from __future__ import annotations

import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

try:
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Histogram,
        Gauge,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

# ── Registry & Metrics ──────────────────────────────────────────

if PROMETHEUS_AVAILABLE:
    REGISTRY = CollectorRegistry()

    REQUEST_COUNT = Counter(
        "agentmemorydb_http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status_code"],
        registry=REGISTRY,
    )

    REQUEST_LATENCY = Histogram(
        "agentmemorydb_http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "path"],
        buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        registry=REGISTRY,
    )

    MEMORY_UPSERTS = Counter(
        "agentmemorydb_memory_upserts_total",
        "Total memory upsert operations",
        ["action"],  # created | updated | skipped
        registry=REGISTRY,
    )

    MEMORY_SEARCHES = Counter(
        "agentmemorydb_memory_searches_total",
        "Total memory search operations",
        ["strategy"],  # hybrid_vector | metadata_only
        registry=REGISTRY,
    )

    ACTIVE_MEMORIES = Gauge(
        "agentmemorydb_active_memories",
        "Current number of active memories (updated periodically)",
        registry=REGISTRY,
    )

    WEBHOOK_DELIVERIES = Counter(
        "agentmemorydb_webhook_deliveries_total",
        "Total webhook delivery attempts",
        ["event_type", "success"],
        registry=REGISTRY,
    )


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Instrument HTTP requests with Prometheus metrics."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not PROMETHEUS_AVAILABLE:
            return await call_next(request)

        # Normalise path to avoid cardinality explosion
        path = request.url.path
        # Strip UUIDs from paths for metric labels
        import re
        path = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "{id}",
            path,
        )

        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        REQUEST_COUNT.labels(
            method=request.method,
            path=path,
            status_code=response.status_code,
        ).inc()

        REQUEST_LATENCY.labels(
            method=request.method,
            path=path,
        ).observe(elapsed)

        return response


def metrics_response() -> Response:
    """Generate Prometheus metrics response."""
    if not PROMETHEUS_AVAILABLE:
        return Response(
            content="prometheus_client not installed",
            media_type="text/plain",
            status_code=501,
        )
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )


def record_upsert(action: str) -> None:
    """Record a memory upsert metric."""
    if PROMETHEUS_AVAILABLE:
        MEMORY_UPSERTS.labels(action=action).inc()


def record_search(strategy: str) -> None:
    """Record a memory search metric."""
    if PROMETHEUS_AVAILABLE:
        MEMORY_SEARCHES.labels(strategy=strategy).inc()


def record_webhook_delivery(event_type: str, success: bool) -> None:
    """Record a webhook delivery metric."""
    if PROMETHEUS_AVAILABLE:
        WEBHOOK_DELIVERIES.labels(event_type=event_type, success=str(success)).inc()
