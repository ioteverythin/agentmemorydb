"""Unit tests for API key authentication utilities."""

from __future__ import annotations

import pytest

from app.core.auth import generate_api_key, hash_api_key


@pytest.mark.unit
class TestAPIKeyGeneration:
    def test_generate_key_has_prefix(self):
        raw_key, _key_hash, _key_prefix = generate_api_key()
        assert raw_key.startswith("amdb_")

    def test_generate_key_is_unique(self):
        keys = {generate_api_key()[0] for _ in range(100)}
        assert len(keys) == 100

    def test_hash_is_deterministic(self):
        raw_key, _, _ = generate_api_key()
        h1 = hash_api_key(raw_key)
        h2 = hash_api_key(raw_key)
        assert h1 == h2

    def test_hash_differs_for_different_keys(self):
        k1, _, _ = generate_api_key()
        k2, _, _ = generate_api_key()
        assert hash_api_key(k1) != hash_api_key(k2)

    def test_key_length(self):
        raw_key, _, _ = generate_api_key()
        # amdb_ prefix (5) + base64-urlsafe token (43 chars for 32 bytes)
        assert len(raw_key) > 40

    def test_key_prefix_matches(self):
        raw_key, _, key_prefix = generate_api_key()
        assert raw_key.startswith(key_prefix)

    def test_hash_matches(self):
        raw_key, key_hash, _ = generate_api_key()
        assert hash_api_key(raw_key) == key_hash
