"""HTTP-level (ASGI) tests for the memory endpoints.

These drive the real FastAPI app through httpx.ASGITransport — exercising
request validation, dependency injection, the auth dependency, and response
models end to end — which the service-level unit tests do not cover. The app's
``get_session`` dependency is overridden to a shared in-memory SQLite engine;
lifespan events (scheduler, provider selection) are not run by ASGITransport,
so no PostgreSQL is required.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.auth import hash_api_key
from app.core.config import settings
from app.db.session import get_session
from app.main import app
from app.models.api_key import APIKey
from tests.conftest import _sqlite_create_all


@pytest_asyncio.fixture
async def api() -> AsyncGenerator[tuple[httpx.AsyncClient, async_sessionmaker], None]:
    # One shared connection so data seeded/committed between requests persists.
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(_sqlite_create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_session] = _override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, factory

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.unit
class TestAssembleContextEndpoint:
    @pytest.mark.asyncio
    async def test_assemble_context_happy_path(self, api):
        client, _ = api
        user_id = str(uuid.uuid4())

        for key, content, layer in [
            ("persona1", "The user is a staff engineer who values brevity.", "persona"),
            ("atom1", "The auth service owner is team-identity.", "atom"),
        ]:
            r = await client.post(
                "/api/v1/memories/upsert",
                json={
                    "user_id": user_id,
                    "memory_key": key,
                    "memory_type": "semantic",
                    "layer": layer,
                    "content": content,
                },
            )
            assert r.status_code == 200, r.text

        r = await client.post(
            "/api/v1/memories/assemble-context",
            json={"user_id": user_id, "query_text": "auth owner", "top_k": 10},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["included_count"] >= 1
        assert "<memory-context>" in body["context"]
        assert body["token_estimate"] == len(body["context"]) // 4
        # Every included memory is wrapped in exactly one untrusted fence.
        assert body["context"].count("</untrusted-memory>") == body["included_count"]

    @pytest.mark.asyncio
    async def test_assemble_context_empty(self, api):
        client, _ = api
        r = await client.post(
            "/api/v1/memories/assemble-context",
            json={"user_id": str(uuid.uuid4()), "query_text": "nothing", "top_k": 5},
        )
        assert r.status_code == 200, r.text
        assert r.json()["context"] == ""


@pytest.mark.unit
class TestTenantIsolationOverHttp:
    @pytest.mark.asyncio
    async def test_mismatched_user_is_forbidden(self, api):
        client, factory = api
        owner_id = uuid.uuid4()
        raw_key = "amdb_test_owner_key"

        async with factory() as s:
            s.add(
                APIKey(
                    id=uuid.uuid4(),
                    user_id=owner_id,
                    name="owner",
                    key_hash=hash_api_key(raw_key),
                    key_prefix=raw_key[:12],
                    scopes="memory:read,memory:write",
                    is_active=True,
                )
            )
            await s.commit()

        prev_auth = settings.require_auth
        prev_iso = settings.enforce_tenant_isolation
        settings.require_auth = True
        settings.enforce_tenant_isolation = True
        try:
            # A key for owner_id cannot search another user's memories.
            r = await client.post(
                "/api/v1/memories/search",
                headers={"X-API-Key": raw_key},
                json={"user_id": str(uuid.uuid4()), "query_text": "x", "top_k": 5},
            )
            assert r.status_code == 403, r.text

            # The owner acting on their own user_id is allowed.
            r_ok = await client.post(
                "/api/v1/memories/search",
                headers={"X-API-Key": raw_key},
                json={"user_id": str(owner_id), "query_text": "x", "top_k": 5},
            )
            assert r_ok.status_code == 200, r_ok.text

            # Missing key when auth is required → 401.
            r_401 = await client.post(
                "/api/v1/memories/search",
                json={"user_id": str(owner_id), "query_text": "x", "top_k": 5},
            )
            assert r_401.status_code == 401, r_401.text
        finally:
            settings.require_auth = prev_auth
            settings.enforce_tenant_isolation = prev_iso
