"""Tests for MCP tool correctness fixes (record_event, consolidate dry_run,
and vocabulary alignment with the server enums)."""

from __future__ import annotations

import contextlib
import uuid

import pytest

from app.mcp import tools as mcp_tools
from app.mcp.tools import TOOL_REGISTRY, handle_consolidate_memories
from app.models.enums import EventType, SourceType
from app.models.user import User
from app.schemas.memory import MemoryUpsert
from app.services.memory_service import MemoryService


@pytest.mark.unit
class TestMcpVocabulary:
    def test_record_event_requires_run_id(self):
        # Events are run-scoped (Event.run_id is NOT NULL) — run_id must be required.
        required = TOOL_REGISTRY["record_event"].input_schema["required"]
        assert "run_id" in required

    def test_record_event_uses_server_event_types(self):
        schema = TOOL_REGISTRY["record_event"].input_schema
        enum = set(schema["properties"]["event_type"]["enum"])
        assert enum == {e.value for e in EventType}

    def test_store_memory_uses_server_source_types(self):
        schema = TOOL_REGISTRY["store_memory"].input_schema
        enum = set(schema["properties"]["source_type"]["enum"])
        assert enum == {s.value for s in SourceType}

    def test_store_memory_exposes_layer(self):
        schema = TOOL_REGISTRY["store_memory"].input_schema
        assert set(schema["properties"]["layer"]["enum"]) == {"raw", "atom", "scenario", "persona"}


@pytest.mark.unit
class TestConsolidateDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_reports_without_merging(self, unit_session, monkeypatch):
        """dry_run=True must detect duplicates but leave every memory active."""
        user_id = uuid.uuid4()
        unit_session.add(User(id=user_id, name="dry-run-user"))
        await unit_session.flush()

        svc = MemoryService(unit_session)
        # Two memories with identical content → identical content_hash → duplicates.
        for key in ("a", "b"):
            await svc.upsert(
                MemoryUpsert(
                    user_id=user_id,
                    memory_key=key,
                    memory_type="semantic",
                    content="the sky is blue",
                )
            )
        await unit_session.flush()

        # Point the handler's session factory at the in-memory test session.
        @contextlib.asynccontextmanager
        async def _fake_factory():
            yield unit_session

        monkeypatch.setattr(mcp_tools, "async_session_factory", _fake_factory)

        result = await handle_consolidate_memories({"user_id": str(user_id), "dry_run": True})

        assert result["dry_run"] is True
        assert result["duplicates_found"] == 1
        assert result["merged"] == 0
        assert len(result["details"]) == 1

        # Nothing archived — the preview did not mutate.
        mems = await svc.list_memories(user_id=user_id)
        assert all(m.status == "active" for m in mems)
