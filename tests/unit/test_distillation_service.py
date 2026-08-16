"""Tests for the self-filling pyramid (atom → scenario → persona)."""

from __future__ import annotations

import uuid

import pytest

from app.models.user import User
from app.schemas.memory import MemoryUpsert
from app.services.distillation_service import DistillationService
from app.services.memory_service import MemoryService


async def _user(session) -> uuid.UUID:
    uid = uuid.uuid4()
    session.add(User(id=uid, name="distill-user"))
    await session.flush()
    return uid


async def _atom(svc, user_id, key, content, importance=0.6):
    await svc.upsert(
        MemoryUpsert(
            user_id=user_id,
            memory_key=key,
            memory_type="semantic",
            layer="atom",
            content=content,
            importance_score=importance,
        )
    )


@pytest.mark.unit
class TestDistillation:
    async def _seed(self, session):
        user_id = await _user(session)
        svc = MemoryService(session)
        await _atom(svc, user_id, "pref:language", "Codes in Python.", 0.9)
        await _atom(svc, user_id, "pref:style", "Prefers spaces over tabs.", 0.8)
        await _atom(svc, user_id, "fact:role", "Staff backend engineer.", 0.85)  # lone topic
        await session.flush()
        return user_id

    @pytest.mark.asyncio
    async def test_atoms_group_into_scenario(self, unit_session):
        user_id = await self._seed(unit_session)
        report = await DistillationService(unit_session).distill(user_id)

        # 'pref' has 2 atoms → a scenario; 'fact' has 1 → below min_group_size.
        topics = {s["topic"] for s in report["scenarios"]}
        assert topics == {"pref"}
        assert report["atoms_considered"] == 3

        mems = await MemoryService(unit_session).list_memories(user_id=user_id)
        by_key = {m.memory_key: m for m in mems}
        assert "scenario:pref" in by_key
        scenario = by_key["scenario:pref"]
        assert scenario.layer == "scenario"
        assert "Python" in scenario.content and "spaces" in scenario.content
        assert scenario.payload["kind"] == "distilled"
        assert set(scenario.payload["distilled_from"]) == {"pref:language", "pref:style"}

    @pytest.mark.asyncio
    async def test_persona_synthesised(self, unit_session):
        user_id = await self._seed(unit_session)
        report = await DistillationService(unit_session).distill(user_id)
        assert report["persona_updated"] is True

        mems = {
            m.memory_key: m
            for m in await MemoryService(unit_session).list_memories(user_id=user_id)
        }
        assert "persona:core" in mems
        assert mems["persona:core"].layer == "persona"

    @pytest.mark.asyncio
    async def test_idempotent_rerun_versions(self, unit_session):
        user_id = await self._seed(unit_session)
        svc = DistillationService(unit_session)
        await svc.distill(user_id)
        await svc.distill(user_id)  # second run updates same keys

        mems = {
            m.memory_key: m
            for m in await MemoryService(unit_session).list_memories(user_id=user_id)
        }
        # Only one scenario:pref (updated, not duplicated).
        assert sum(1 for k in mems if k == "scenario:pref") == 1
        # Content identical across runs → skip-identical keeps version at 1.
        assert mems["scenario:pref"].version == 1

    @pytest.mark.asyncio
    async def test_dry_run_writes_nothing(self, unit_session):
        user_id = await self._seed(unit_session)
        report = await DistillationService(unit_session).distill(user_id, dry_run=True)
        assert report["dry_run"] is True
        assert report["scenarios"]  # still reports what would be produced

        mems = {
            m.memory_key for m in await MemoryService(unit_session).list_memories(user_id=user_id)
        }
        assert "scenario:pref" not in mems
        assert "persona:core" not in mems
