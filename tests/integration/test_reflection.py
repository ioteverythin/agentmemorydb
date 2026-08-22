"""Integration: reflection against real PostgreSQL.

Two things only the real engine exercises: pgvector-typed embeddings feeding the
clustering, and the JSONB ``details`` column round-tripping the per-cluster
report that operators actually read.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.consolidation_run import ConsolidationRun
from app.models.memory import Memory
from app.models.memory_link import MemoryLink
from app.models.user import User
from app.services.reflection_service import ReflectionService
from app.utils.embedding_provider import get_embedding_provider
from app.utils.llm_provider import BaseLLMProvider, NullLLMProvider, set_llm_provider

pytestmark = pytest.mark.integration


class StubLLM(BaseLLMProvider):
    def __init__(self, reply: str) -> None:
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


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "enable_reflection", True)


async def _seed(session) -> uuid.UUID:
    user_id = uuid.uuid4()
    session.add(User(id=user_id, name="reflect-int"))
    await session.flush()

    # Real pgvector values, all pointing the same way so they cluster. The
    # dimension is taken from the active provider rather than hardcoded — the
    # column's width is whatever the test database was built with.
    probe = (await get_embedding_provider().embed(["probe"]))[0]
    vector = [0.0] * len(probe)
    vector[0] = 1.0
    for i in range(3):
        session.add(
            Memory(
                id=uuid.uuid4(),
                user_id=user_id,
                memory_key=f"fact:pg-{i}",
                memory_type="semantic",
                layer="atom",
                content=f"Uses Postgres for service {i}.",
                content_hash=f"reflect-int-{i}",
                status="active",
                embedding=vector,
                confidence=0.7,
                importance_score=0.5,
                authority_level=1,
            )
        )
    await session.flush()
    return user_id


@pytest.mark.asyncio
async def test_reflection_writes_a_traceable_insight(integration_session, enabled):
    session = integration_session
    user_id = await _seed(session)
    set_llm_provider(StubLLM("The user is standardising their services on Postgres."))

    run = await ReflectionService(session).reflect(user_id)
    await session.flush()

    assert run.status == "completed"
    assert run.clusters_found == 1
    assert run.insights_created == 1

    # JSONB details survive the round trip.
    stored = await session.get(ConsolidationRun, run.id)
    assert stored is not None
    assert stored.details["clusters"][0]["size"] == 3
    assert len(stored.details["clusters"][0]["sources"]) == 3

    insight = (
        (await session.execute(select(Memory).where(Memory.memory_key.like("reflection:%"))))
        .scalars()
        .one()
    )
    assert insight.layer == "scenario"
    assert insight.origin == "system"

    links = (
        (await session.execute(select(MemoryLink).where(MemoryLink.source_memory_id == insight.id)))
        .scalars()
        .all()
    )
    assert len(links) == 3


@pytest.mark.asyncio
async def test_no_llm_records_a_skip_row(integration_session, enabled):
    session = integration_session
    user_id = await _seed(session)

    run = await ReflectionService(session).reflect(user_id)
    await session.flush()

    assert run.status == "skipped"
    assert run.skipped_reason == "no_llm_provider"
    assert (await session.get(ConsolidationRun, run.id)) is not None
