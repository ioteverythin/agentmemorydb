"""Integration: the self-filling pyramid + retention forgetting on PostgreSQL."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.memory import Memory
from app.models.user import User
from app.schemas.memory import MemorySearchRequest, MemoryUpsert
from app.services.distillation_service import DistillationService
from app.services.forgetting_service import ForgettingService
from app.services.memory_service import MemoryService
from app.services.retrieval_service import RetrievalService

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_distillation_end_to_end(integration_session):
    session = integration_session
    user_id = uuid.uuid4()
    session.add(User(id=user_id, name="distill-int"))
    await session.flush()

    svc = MemoryService(session)
    for key, content in [
        ("pref:language", "Codes primarily in Python."),
        ("pref:style", "Prefers spaces over tabs."),
        ("stack:db", "Uses PostgreSQL with pgvector."),
        ("stack:queue", "Uses Redis for queues."),
    ]:
        await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key=key,
                memory_type="semantic",
                layer="atom",
                content=content,
                importance_score=0.7,
            )
        )
    await session.flush()

    report = await DistillationService(session).distill(user_id)
    topics = {s["topic"] for s in report["scenarios"]}
    assert topics == {"pref", "stack"}
    assert report["persona_updated"] is True
    await session.flush()

    # The distilled scenario is retrievable and lives on the scenario layer.
    resp = await RetrievalService(session).search(
        MemorySearchRequest(
            user_id=user_id, query_text="postgres redis", layers=["scenario"], top_k=5
        )
    )
    assert {"stack" in r.memory.memory_key for r in resp.results}
    assert all(r.memory.layer == "scenario" for r in resp.results)


@pytest.mark.asyncio
async def test_forgetting_archives_low_retention(integration_session):
    session = integration_session
    user_id = uuid.uuid4()
    session.add(User(id=user_id, name="forget-int"))
    await session.flush()

    old = datetime.now(UTC) - timedelta(days=60)
    session.add(
        Memory(
            id=uuid.uuid4(),
            user_id=user_id,
            memory_key="junk",
            memory_type="semantic",
            layer="atom",
            content="stale trivia",
            content_hash="junkhash",
            status="active",
            importance_score=0.1,
            confidence=0.5,
            authority_level=1,
            recency_score=1.0,
            version=1,
            created_at=old,
            updated_at=old,
        )
    )
    await session.flush()

    report = await ForgettingService(session).archive_low_retention()
    assert report["archived"] >= 1

    from sqlalchemy import select

    m = (await session.execute(select(Memory).where(Memory.memory_key == "junk"))).scalars().first()
    assert m.status == "archived"
