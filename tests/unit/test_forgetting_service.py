"""Tests for importance/access-aware forgetting (retention-based archival)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.memory import Memory
from app.models.memory_access_log import MemoryAccessLog
from app.models.user import User
from app.services.forgetting_service import ForgettingService


async def _user(session) -> uuid.UUID:
    uid = uuid.uuid4()
    session.add(User(id=uid, name="forget-user"))
    await session.flush()
    return uid


def _mem(user_id, key, *, importance, age_days, layer="atom") -> Memory:
    ts = datetime.now(UTC) - timedelta(days=age_days)
    return Memory(
        id=uuid.uuid4(),
        user_id=user_id,
        memory_key=key,
        memory_type="semantic",
        layer=layer,
        content=key,
        content_hash=key,
        status="active",
        importance_score=importance,
        confidence=0.5,
        authority_level=1,
        recency_score=1.0,
        version=1,
        created_at=ts,
        updated_at=ts,
    )


@pytest.mark.unit
class TestForgetting:
    @pytest.mark.asyncio
    async def test_stale_low_value_is_archived(self, unit_session):
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "junk", importance=0.1, age_days=60))
        await unit_session.flush()

        report = await ForgettingService(unit_session).archive_low_retention()
        assert report["archived"] == 1

        m = await unit_session.get(Memory, (await _first(unit_session, "junk")).id)
        assert m.status == "archived"

    @pytest.mark.asyncio
    async def test_recent_or_important_is_kept(self, unit_session):
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "fresh", importance=0.1, age_days=1))  # too young
        unit_session.add(_mem(user_id, "important", importance=0.95, age_days=60))
        await unit_session.flush()

        await ForgettingService(unit_session).archive_low_retention()
        for key in ("fresh", "important"):
            m = await _first(unit_session, key)
            assert m.status == "active"

    @pytest.mark.asyncio
    async def test_frequently_accessed_is_kept(self, unit_session):
        user_id = await _user(unit_session)
        hot = _mem(user_id, "hot", importance=0.1, age_days=60)
        unit_session.add(hot)
        await unit_session.flush()
        # Log several accesses → high access signal → retained.
        for _ in range(15):
            unit_session.add(MemoryAccessLog(memory_id=hot.id, user_id=user_id))
        await unit_session.flush()

        await ForgettingService(unit_session).archive_low_retention()
        assert (await _first(unit_session, "hot")).status == "active"

    @pytest.mark.asyncio
    async def test_distilled_layers_are_exempt(self, unit_session):
        user_id = await _user(unit_session)
        # Old, low-importance persona — would be archived if not exempt.
        unit_session.add(
            _mem(user_id, "persona:core", importance=0.1, age_days=90, layer="persona")
        )
        await unit_session.flush()

        await ForgettingService(unit_session).archive_low_retention()
        assert (await _first(unit_session, "persona:core")).status == "active"

    @pytest.mark.asyncio
    async def test_dry_run_does_not_archive(self, unit_session):
        user_id = await _user(unit_session)
        unit_session.add(_mem(user_id, "junk", importance=0.1, age_days=60))
        await unit_session.flush()

        report = await ForgettingService(unit_session).archive_low_retention(dry_run=True)
        assert report["archived"] == 1
        assert (await _first(unit_session, "junk")).status == "active"


async def _first(session, key) -> Memory:
    from sqlalchemy import select

    return (await session.execute(select(Memory).where(Memory.memory_key == key))).scalars().first()
