"""Unit tests for the SDK client construction."""

from __future__ import annotations

import pytest

from app.sdk.client import AgentMemoryDBClient, AgentMemoryDBError


@pytest.mark.unit
class TestSDKClient:
    def test_default_base_url(self):
        client = AgentMemoryDBClient()
        assert "localhost:8100" in str(client._client.base_url)

    def test_custom_base_url(self):
        client = AgentMemoryDBClient(base_url="http://my-server:9000")
        assert "my-server:9000" in str(client._client.base_url)

    def test_api_key_header(self):
        client = AgentMemoryDBClient(api_key="test-key-123")
        assert client._client.headers["X-API-Key"] == "test-key-123"

    def test_error_class(self):
        err = AgentMemoryDBError(500, {"detail": "boom"})
        assert err.status_code == 500
        assert "boom" in str(err)
