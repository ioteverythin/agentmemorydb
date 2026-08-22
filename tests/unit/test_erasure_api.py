"""HTTP-level tests for the erasure endpoints and the `erase` scope gate.

Erasure is irreversible, so the scope check is the safety boundary and is worth
testing through the real ASGI stack rather than at the service level: a key
without ``erase`` must be refused, and the default ``DELETE`` must not delete.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.auth import hash_api_key
from app.core.config import settings
from app.db.session import get_session
from app.main import app
from app.models.api_key import APIKey
from app.models.forgetting_log import ForgettingLog
from app.models.memory import Memory
from app.models.user import User
from tests.conftest import _sqlite_create_all

RAW_KEY = "amdb_test_erase_key"


@pytest_asyncio.fixture
async def api() -> AsyncGenerator[tuple[httpx.AsyncClient, async_sessionmaker], None]:
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


async def _seed(factory, *, scopes: str | None) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed a user, one memory, and an API key with the given scopes."""
    user_id = uuid.uuid4()
    memory_id = uuid.uuid4()
    async with factory() as s:
        s.add(User(id=user_id, name="erase-user"))
        s.add(
            Memory(
                id=memory_id,
                user_id=user_id,
                memory_key="pref:secret",
                memory_type="semantic",
                content="Sensitive personal detail.",
                content_hash="hash-secret",
                status="active",
            )
        )
        s.add(
            APIKey(
                id=uuid.uuid4(),
                user_id=user_id,
                name="erase-key",
                key_hash=hash_api_key(RAW_KEY),
                key_prefix=RAW_KEY[:12],
                scopes=scopes,
                is_active=True,
            )
        )
        await s.commit()
    return user_id, memory_id


@pytest.mark.unit
class TestEraseScope:
    @pytest.mark.asyncio
    async def test_erase_requires_erase_scope(self, api):
        client, factory = api
        _user_id, memory_id = await _seed(factory, scopes="memory:read,memory:write")

        prev = settings.require_auth
        settings.require_auth = True
        try:
            r = await client.delete(
                f"/api/v1/memories/{memory_id}?mode=erase",
                headers={"X-API-Key": RAW_KEY},
            )
            assert r.status_code == 403, r.text
            assert "erase" in r.json()["detail"]
        finally:
            settings.require_auth = prev

        # Nothing was deleted.
        async with factory() as s:
            assert await s.get(Memory, memory_id) is not None

    @pytest.mark.asyncio
    async def test_unscoped_key_cannot_erase(self, api):
        """A blank `scopes` is unrestricted elsewhere but never grants erasure."""
        client, factory = api
        _user_id, memory_id = await _seed(factory, scopes=None)

        prev = settings.require_auth
        settings.require_auth = True
        try:
            r = await client.delete(
                f"/api/v1/memories/{memory_id}?mode=erase",
                headers={"X-API-Key": RAW_KEY},
            )
            assert r.status_code == 403, r.text
        finally:
            settings.require_auth = prev

    @pytest.mark.asyncio
    async def test_erase_with_scope_deletes_and_logs(self, api):
        client, factory = api
        user_id, memory_id = await _seed(factory, scopes="memory:read,erase")

        prev = settings.require_auth
        settings.require_auth = True
        try:
            r = await client.delete(
                f"/api/v1/memories/{memory_id}?mode=erase&reason=gdpr+request",
                headers={"X-API-Key": RAW_KEY},
            )
            assert r.status_code == 200, r.text
            assert r.json()["erased"] == 1
        finally:
            settings.require_auth = prev

        async with factory() as s:
            assert await s.get(Memory, memory_id) is None
            rows = (await s.execute(select(ForgettingLog))).scalars().all()
            assert len(rows) == 1
            assert rows[0].action == "user_erasure"
            assert rows[0].content_hash == "hash-secret"
            assert rows[0].reason == "gdpr request"
            assert rows[0].user_id == user_id

    @pytest.mark.asyncio
    async def test_default_delete_archives_instead_of_erasing(self, api):
        """DELETE without ?mode=erase must be non-destructive."""
        client, factory = api
        _user_id, memory_id = await _seed(factory, scopes=None)

        r = await client.delete(f"/api/v1/memories/{memory_id}")
        assert r.status_code == 200, r.text
        assert r.json()["erased"] == 0

        async with factory() as s:
            memory = await s.get(Memory, memory_id)
            assert memory is not None
            assert memory.status == "archived"

    @pytest.mark.asyncio
    async def test_erase_all_user_memories_requires_scope(self, api):
        client, factory = api
        user_id, memory_id = await _seed(factory, scopes="memory:read")

        prev = settings.require_auth
        settings.require_auth = True
        try:
            r = await client.delete(
                f"/api/v1/users/{user_id}/memories?mode=erase",
                headers={"X-API-Key": RAW_KEY},
            )
            assert r.status_code == 403, r.text
        finally:
            settings.require_auth = prev

        async with factory() as s:
            assert await s.get(Memory, memory_id) is not None

    @pytest.mark.asyncio
    async def test_erase_all_user_memories_with_scope(self, api):
        client, factory = api
        user_id, memory_id = await _seed(factory, scopes="erase")

        prev = settings.require_auth
        settings.require_auth = True
        try:
            r = await client.delete(
                f"/api/v1/users/{user_id}/memories?mode=erase",
                headers={"X-API-Key": RAW_KEY},
            )
            assert r.status_code == 200, r.text
            assert r.json()["erased"] == 1
        finally:
            settings.require_auth = prev

        async with factory() as s:
            assert await s.get(Memory, memory_id) is None


@pytest.mark.unit
class TestPinAndLogEndpoints:
    @pytest.mark.asyncio
    async def test_pin_endpoint_toggles_pinned(self, api):
        client, factory = api
        _user_id, memory_id = await _seed(factory, scopes=None)

        r = await client.patch(f"/api/v1/memories/{memory_id}/pin", json={"pinned": True})
        assert r.status_code == 200, r.text
        assert r.json()["pinned"] is True

        r = await client.patch(f"/api/v1/memories/{memory_id}/pin", json={"pinned": False})
        assert r.json()["pinned"] is False

    @pytest.mark.asyncio
    async def test_forgetting_log_endpoint(self, api):
        client, factory = api
        user_id, memory_id = await _seed(factory, scopes="erase")

        await client.delete(f"/api/v1/memories/{memory_id}?mode=erase")

        r = await client.get(f"/api/v1/forgetting/log?user_id={user_id}")
        assert r.status_code == 200, r.text
        entries = r.json()
        assert len(entries) == 1
        assert entries[0]["action"] == "user_erasure"
        assert entries[0]["memory_id"] == str(memory_id)

    @pytest.mark.asyncio
    async def test_decay_endpoint_defaults_to_dry_run(self, api):
        client, factory = api
        await _seed(factory, scopes=None)

        r = await client.post("/api/v1/forgetting/decay")
        assert r.status_code == 200, r.text
        assert r.json()["dry_run"] is True
