"""Unit tests for middleware components."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.middleware import RequestIDMiddleware, TimingMiddleware


@pytest.fixture
def test_app() -> FastAPI:
    """Minimal app with both middleware layers."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(TimingMiddleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return app


@pytest.mark.unit
class TestRequestIDMiddleware:
    @pytest.mark.asyncio
    async def test_adds_request_id_header(self, test_app):
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            resp = await client.get("/ping")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers
        # Must be a valid UUID-like string
        rid = resp.headers["x-request-id"]
        assert len(rid) > 10

    @pytest.mark.asyncio
    async def test_preserves_provided_request_id(self, test_app):
        custom_id = "my-custom-request-id-123"
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            resp = await client.get("/ping", headers={"X-Request-ID": custom_id})
        assert resp.headers["x-request-id"] == custom_id


@pytest.mark.unit
class TestTimingMiddleware:
    @pytest.mark.asyncio
    async def test_adds_process_time_header(self, test_app):
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            resp = await client.get("/ping")
        assert resp.status_code == 200
        assert "x-process-time-ms" in resp.headers
        elapsed = float(resp.headers["x-process-time-ms"])
        assert elapsed >= 0
