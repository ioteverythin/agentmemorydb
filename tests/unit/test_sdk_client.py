"""Unit tests for the SDK client construction."""

from __future__ import annotations

import pytest

from app.sdk.client import EngramDBClient, EngramDBError


@pytest.mark.unit
class TestSDKClient:
    def test_default_base_url(self):
        client = EngramDBClient()
        assert "localhost:8100" in str(client._client.base_url)

    def test_custom_base_url(self):
        client = EngramDBClient(base_url="http://my-server:9000")
        assert "my-server:9000" in str(client._client.base_url)

    def test_api_key_header(self):
        client = EngramDBClient(api_key="test-key-123")
        assert client._client.headers["X-API-Key"] == "test-key-123"

    def test_error_class(self):
        err = EngramDBError(500, {"detail": "boom"})
        assert err.status_code == 500
        assert "boom" in str(err)
