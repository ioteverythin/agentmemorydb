"""Tests for API-key tenant isolation (enforce_tenant)."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.core.auth import enforce_tenant
from app.core.config import settings
from app.models.api_key import APIKey


def _key(user_id: uuid.UUID, scopes: str | None = None) -> APIKey:
    return APIKey(
        id=uuid.uuid4(),
        user_id=user_id,
        name="k",
        key_hash="h",
        key_prefix="amdb_x",
        scopes=scopes,
        is_active=True,
    )


@pytest.mark.unit
class TestEnforceTenant:
    def test_none_key_is_noop(self):
        # Auth disabled → api_key is None → never raises.
        enforce_tenant(None, uuid.uuid4())

    def test_matching_user_allowed(self):
        uid = uuid.uuid4()
        enforce_tenant(_key(uid), uid)  # no raise

    def test_mismatched_user_forbidden(self):
        enabled = settings.enforce_tenant_isolation
        settings.enforce_tenant_isolation = True
        try:
            with pytest.raises(HTTPException) as exc:
                enforce_tenant(_key(uuid.uuid4()), uuid.uuid4())
            assert exc.value.status_code == 403
        finally:
            settings.enforce_tenant_isolation = enabled

    def test_wildcard_scope_is_cross_tenant(self):
        enabled = settings.enforce_tenant_isolation
        settings.enforce_tenant_isolation = True
        try:
            # A service/admin key with "*" may act for any user_id.
            enforce_tenant(_key(uuid.uuid4(), scopes="*"), uuid.uuid4())
        finally:
            settings.enforce_tenant_isolation = enabled

    def test_disabled_isolation_is_noop(self):
        enabled = settings.enforce_tenant_isolation
        settings.enforce_tenant_isolation = False
        try:
            enforce_tenant(_key(uuid.uuid4()), uuid.uuid4())  # no raise
        finally:
            settings.enforce_tenant_isolation = enabled
