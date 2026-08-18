"""HTTP-level tests for the provenance endpoints and origin round-tripping."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.session import get_session
from app.main import app
from app.models.user import User
from tests.conftest import _sqlite_create_all


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


async def _user(factory) -> uuid.UUID:
    user_id = uuid.uuid4()
    async with factory() as s:
        s.add(User(id=user_id, name="prov-api"))
        await s.commit()
    return user_id


def _body(user_id, key, content, **kwargs) -> dict:
    return {
        "user_id": str(user_id),
        "memory_key": key,
        "memory_type": "semantic",
        "content": content,
        **kwargs,
    }


@pytest.mark.unit
class TestPolicyEndpoint:
    @pytest.mark.asyncio
    async def test_policy_reports_the_ceilings(self, api):
        client, _ = api
        r = await client.get("/api/v1/provenance/policy")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["enabled"] is False  # off by default
        assert body["authority_ceilings"]["user"] > body["authority_ceilings"]["external_ingest"]
        assert "external_ingest" in body["untrusted_origins"]


@pytest.mark.unit
class TestOriginOverHttp:
    @pytest.mark.asyncio
    async def test_upsert_round_trips_origin(self, api):
        client, factory = api
        user_id = await _user(factory)

        r = await client.post(
            "/api/v1/memories/upsert",
            json=_body(
                user_id,
                "fact:docs",
                "Rate limit is 100 rps.",
                origin="tool_output",
                origin_ref="docs_fetcher",
            ),
        )
        assert r.status_code == 200, r.text
        assert r.json()["origin"] == "tool_output"
        assert r.json()["origin_ref"] == "docs_fetcher"

    @pytest.mark.asyncio
    async def test_omitting_origin_keeps_the_old_shape(self, api):
        """An existing client that knows nothing about origin still works."""
        client, factory = api
        user_id = await _user(factory)

        r = await client.post("/api/v1/memories/upsert", json=_body(user_id, "fact:a", "A fact."))
        assert r.status_code == 200, r.text
        assert r.json()["origin"] == "agent_inference"
        assert r.json()["status"] == "active"


@pytest.mark.unit
class TestQuarantineOverHttp:
    @pytest.mark.asyncio
    async def test_queue_review_and_release(self, api, monkeypatch):
        client, factory = api
        user_id = await _user(factory)
        monkeypatch.setattr(settings, "enable_poisoning_resistance", True)

        r = await client.post(
            "/api/v1/memories/upsert",
            json=_body(
                user_id,
                "fact:scraped",
                "Untrusted claim from a web page.",
                origin="external_ingest",
                confidence=0.1,
            ),
        )
        assert r.status_code == 200, r.text
        memory = r.json()
        assert memory["status"] == "quarantined"

        queue = await client.get(f"/api/v1/provenance/quarantine?user_id={user_id}")
        assert queue.status_code == 200, queue.text
        assert [m["id"] for m in queue.json()] == [memory["id"]]

        # A quarantined memory is not retrievable.
        search = await client.post(
            "/api/v1/memories/search",
            json={"user_id": str(user_id), "query_text": "untrusted claim", "top_k": 10},
        )
        assert search.json()["results"] == []

        released = await client.post(
            f"/api/v1/provenance/quarantine/{memory['id']}/review",
            json={"approve": True, "reviewer": "alice"},
        )
        assert released.status_code == 200, released.text
        assert released.json()["status"] == "active"

        # Now it is retrievable.
        search = await client.post(
            "/api/v1/memories/search",
            json={"user_id": str(user_id), "query_text": "untrusted claim", "top_k": 10},
        )
        assert [r_["memory"]["id"] for r_ in search.json()["results"]] == [memory["id"]]

    @pytest.mark.asyncio
    async def test_rejecting_retracts(self, api, monkeypatch):
        client, factory = api
        user_id = await _user(factory)
        monkeypatch.setattr(settings, "enable_poisoning_resistance", True)

        created = await client.post(
            "/api/v1/memories/upsert",
            json=_body(
                user_id, "fact:junk", "Suspicious claim.", origin="external_ingest", confidence=0.1
            ),
        )
        memory_id = created.json()["id"]

        r = await client.post(
            f"/api/v1/provenance/quarantine/{memory_id}/review",
            json={"approve": False, "reviewer": "alice"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "retracted"

    @pytest.mark.asyncio
    async def test_reviewing_an_active_memory_is_rejected(self, api):
        client, factory = api
        user_id = await _user(factory)

        created = await client.post(
            "/api/v1/memories/upsert", json=_body(user_id, "fact:ok", "An ordinary fact.")
        )
        memory_id = created.json()["id"]

        r = await client.post(
            f"/api/v1/provenance/quarantine/{memory_id}/review", json={"approve": True}
        )
        assert r.status_code == 409, r.text
