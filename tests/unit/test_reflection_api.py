"""HTTP-level tests for the reflection endpoints."""

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
from app.models.memory import Memory
from app.models.user import User
from app.utils.llm_provider import BaseLLMProvider, NullLLMProvider, set_llm_provider
from tests.conftest import _sqlite_create_all


class StubLLM(BaseLLMProvider):
    def __init__(self, reply: str = "The user is standardising on Postgres.") -> None:
        self.reply = reply

    @property
    def available(self) -> bool:
        return True

    async def complete(self, prompt: str, *, system: str | None = None) -> str:
        return self.reply


@pytest.fixture(autouse=True)
def _reset_llm():
    set_llm_provider(NullLLMProvider())
    yield
    set_llm_provider(NullLLMProvider())


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


async def _seed(factory) -> uuid.UUID:
    user_id = uuid.uuid4()
    async with factory() as s:
        s.add(User(id=user_id, name="reflect-api"))
        for i in range(3):
            s.add(
                Memory(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    memory_key=f"fact:pg-{i}",
                    memory_type="semantic",
                    layer="atom",
                    content=f"Uses Postgres for service {i}.",
                    content_hash=f"hash-{i}",
                    status="active",
                    embedding=[1.0, 0.0, 0.0, 0.0],
                )
            )
        await s.commit()
    return user_id


@pytest.mark.unit
class TestReflectionEndpoints:
    @pytest.mark.asyncio
    async def test_reflect_reports_the_skip_reason(self, api, monkeypatch):
        """A pass that did nothing must say which nothing it did."""
        client, factory = api
        user_id = await _seed(factory)
        monkeypatch.setattr(settings, "enable_reflection", True)

        r = await client.post(f"/api/v1/consolidation/reflect?user_id={user_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "skipped"
        assert body["skipped_reason"] == "no_llm_provider"
        assert body["insights_created"] == 0

    @pytest.mark.asyncio
    async def test_disabled_by_default(self, api):
        client, factory = api
        user_id = await _seed(factory)

        r = await client.post(f"/api/v1/consolidation/reflect?user_id={user_id}")
        assert r.json()["skipped_reason"] == "disabled"

    @pytest.mark.asyncio
    async def test_dry_run_clusters_without_writing(self, api, monkeypatch):
        client, factory = api
        user_id = await _seed(factory)
        monkeypatch.setattr(settings, "enable_reflection", True)
        set_llm_provider(StubLLM())

        r = await client.post(f"/api/v1/consolidation/reflect?user_id={user_id}&dry_run=true")
        body = r.json()
        assert body["skipped_reason"] == "dry_run"
        assert body["clusters_found"] == 1

    @pytest.mark.asyncio
    async def test_reflect_then_list_runs(self, api, monkeypatch):
        client, factory = api
        user_id = await _seed(factory)
        monkeypatch.setattr(settings, "enable_reflection", True)
        set_llm_provider(StubLLM("The user is standardising on Postgres."))

        r = await client.post(f"/api/v1/consolidation/reflect?user_id={user_id}")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "completed"
        assert r.json()["insights_created"] == 1

        runs = await client.get(f"/api/v1/consolidation/runs?user_id={user_id}")
        assert runs.status_code == 200, runs.text
        assert len(runs.json()) == 1
        assert runs.json()[0]["kind"] == "reflection"

        # The insight is an ordinary retrievable memory.
        search = await client.post(
            "/api/v1/memories/search",
            json={"user_id": str(user_id), "query_text": "postgres", "top_k": 10},
        )
        keys = [x["memory"]["memory_key"] for x in search.json()["results"]]
        assert any(k.startswith("reflection:") for k in keys)

    @pytest.mark.asyncio
    async def test_scheduler_exposes_the_job(self, api):
        client, _ = api
        r = await client.get("/api/v1/scheduler/jobs")
        assert r.status_code == 200, r.text
        jobs = {j["name"]: j for j in r.json()["jobs"]}
        assert "reflect_and_promote" in jobs
        # Double-gated: registered but disabled while ENABLE_REFLECTION is off.
        assert jobs["reflect_and_promote"]["enabled"] is False
