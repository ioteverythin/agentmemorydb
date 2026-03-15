"""Unit tests for metrics instrumentation (graceful no-op when prometheus not installed)."""

from __future__ import annotations

import pytest

from app.core.metrics import (
    metrics_response,
    record_search,
    record_upsert,
    record_webhook_delivery,
)


@pytest.mark.unit
class TestMetricsNoOp:
    """These should never raise, even without prometheus_client installed."""

    def test_record_upsert_no_error(self):
        record_upsert("create")
        record_upsert("update")
        record_upsert("skip_identical")

    def test_record_search_no_error(self):
        record_search("hybrid_vector")
        record_search("metadata_only")

    def test_record_webhook_no_error(self):
        record_webhook_delivery("memory.created", True)
        record_webhook_delivery("memory.updated", False)

    def test_metrics_response_returns_response(self):
        resp = metrics_response()
        # When prometheus_client is installed, should return 200
        # When not installed, should return 501
        assert resp.status_code in (200, 501)
