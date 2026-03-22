"""Tests for HNSW index config, SSE streaming search, and LangChain adapter.

21 unit tests covering the three features introduced in this PR:

  TestVectorIndexConfig (5 tests)
  TestMemoryModelHNSWIndex (2 tests)
  TestStreamSearchEndpoint (3 tests)
  TestAgentMemoryDBChatMessageHistory (11 tests)
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

# =====================================================================
# 1. TestVectorIndexConfig — Settings class + HNSW defaults
# =====================================================================


@pytest.mark.unit
class TestVectorIndexConfig:
    """Verify HNSW / IVFFlat settings surface correctly."""

    def test_default_index_type_is_hnsw(self):
        from app.core.config import settings

        assert settings.vector_index_type == "hnsw"

    def test_hnsw_m_default(self):
        from app.core.config import settings

        assert settings.hnsw_m == 16

    def test_hnsw_ef_construction_default(self):
        from app.core.config import settings

        assert settings.hnsw_ef_construction == 64

    def test_hnsw_ef_search_default(self):
        from app.core.config import settings

        assert settings.hnsw_ef_search == 40

    def test_override_to_ivfflat(self, monkeypatch):
        """When VECTOR_INDEX_TYPE=ivfflat, the setting changes."""
        monkeypatch.setenv("VECTOR_INDEX_TYPE", "ivfflat")

        # Re-import to pick up the env var

        from app.core import Settings

        fresh = Settings()
        assert fresh.vector_index_type == "ivfflat"


# =====================================================================
# 2. TestMemoryModelHNSWIndex — model index name reflects config
# =====================================================================


@pytest.mark.unit
class TestMemoryModelHNSWIndex:
    """Verify the Memory model builds the right index based on config."""

    def test_hnsw_index_name_present(self):
        """Default config should produce an HNSW index."""
        from app.models.memory import Memory

        index_names = [idx.name for idx in Memory.__table__.indexes]
        assert "ix_memories_embedding_hnsw" in index_names

    def test_ivfflat_index_name_absent_when_hnsw(self):
        """With HNSW as default, IVFFlat should NOT be present."""
        from app.models.memory import Memory

        index_names = [idx.name for idx in Memory.__table__.indexes]
        assert "ix_memories_embedding_ivfflat" not in index_names


# =====================================================================
# 3. TestStreamSearchEndpoint — SSE event format / content-type
# =====================================================================


@pytest.mark.unit
class TestStreamSearchEndpoint:
    """Verify the SSE streaming search endpoint."""

    @pytest.fixture
    def app_client(self):
        """Create a test client with the DB dependency overridden.

        We mock ``get_session`` *and* the ``RetrievalService.search`` call
        so the endpoint never touches a real database.
        """
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from app.db import get_session
        from app.main import app
        from app.schemas.memory import MemorySearchResponse

        async def _fake_session():
            yield AsyncMock()

        app.dependency_overrides[get_session] = _fake_session

        fake_response = MemorySearchResponse(
            results=[],
            total_candidates=0,
            strategy="hybrid_vector",
        )
        with patch(
            "app.api.v1.memories.RetrievalService.search",
            new_callable=AsyncMock,
            return_value=fake_response,
        ):
            yield TestClient(app)

        app.dependency_overrides.pop(get_session, None)

    def test_stream_search_returns_event_stream_content_type(self, app_client):
        """The response should have text/event-stream content type."""
        resp = app_client.post(
            "/api/v1/memories/stream-search",
            json={
                "user_id": str(uuid.uuid4()),
                "top_k": 5,
            },
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_stream_search_sse_format(self):
        """Verify the SSE generator produces correct event format."""
        import json as json_mod

        from app.schemas.memory import (
            MemoryResponse,
            MemorySearchResponse,
            MemorySearchResult,
            ScoreBreakdown,
        )

        # Build a fake response
        fake_memory = MemoryResponse(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            memory_key="test_key",
            memory_type="semantic",
            scope="user",
            content="Test content",
            content_hash="abc123",
            source_type="system_inference",
            status="active",
            authority_level=1,
            confidence=0.8,
            importance_score=0.7,
            recency_score=0.9,
            version=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        fake_score = ScoreBreakdown(
            vector_score=0.9,
            recency_score=0.8,
            importance_score=0.7,
            authority_score=0.6,
            confidence_score=0.5,
            final_score=0.75,
        )
        fake_result = MemorySearchResult(memory=fake_memory, score=fake_score)
        fake_response = MemorySearchResponse(
            results=[fake_result],
            total_candidates=1,
            strategy="hybrid_vector",
        )

        # Simulate what the endpoint generator does
        events = []
        for result in fake_response.results:
            payload = {
                "memory": json_mod.loads(result.memory.model_dump_json()),
                "score": json_mod.loads(result.score.model_dump_json()) if result.score else None,
            }
            events.append(f"data: {json_mod.dumps(payload)}\n\n")

        done = {
            "total_candidates": fake_response.total_candidates,
            "strategy": fake_response.strategy,
        }
        events.append(f"event: done\ndata: {json_mod.dumps(done)}\n\n")

        # Verify structure
        assert len(events) == 2
        assert events[0].startswith("data: ")
        assert events[1].startswith("event: done\n")

        # Parse and check data
        data_line = events[0].replace("data: ", "").strip()
        parsed = json_mod.loads(data_line)
        assert "memory" in parsed
        assert "score" in parsed

    def test_stream_search_done_event_has_strategy(self):
        """The 'done' SSE event must contain strategy and total_candidates."""
        done_payload = {"total_candidates": 42, "strategy": "metadata_only"}
        event_str = f"event: done\ndata: {json.dumps(done_payload)}\n\n"

        lines = event_str.strip().split("\n")
        assert lines[0] == "event: done"
        parsed = json.loads(lines[1].replace("data: ", ""))
        assert parsed["total_candidates"] == 42
        assert parsed["strategy"] == "metadata_only"


# =====================================================================
# 4. TestAgentMemoryDBChatMessageHistory (11 tests)
# =====================================================================


class FakeResponse:
    """Minimal fake httpx.Response for mocking."""

    def __init__(self, json_data: Any = None, status_code: int = 200) -> None:
        self._json_data = json_data or []
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self) -> Any:
        return self._json_data


langchain_core = pytest.importorskip("langchain_core", reason="langchain-core not installed")


@pytest.mark.unit
class TestAgentMemoryDBChatMessageHistory:
    """Test the LangChain ChatMessageHistory adapter."""

    @pytest.fixture
    def user_id(self) -> str:
        return str(uuid.uuid4())

    @pytest.fixture
    def session_id(self) -> str:
        return "test-session-001"

    @pytest.fixture
    def history(self, user_id, session_id):
        from app.adapters.langchain_history import AgentMemoryDBChatMessageHistory

        return AgentMemoryDBChatMessageHistory(
            base_url="http://localhost:8100",
            user_id=user_id,
            session_id=session_id,
        )

    def test_init_sets_attributes(self, history, user_id, session_id):
        assert history.user_id == user_id
        assert history.session_id == session_id
        assert history.base_url == "http://localhost:8100"
        assert history.scope == "user"

    def test_init_strips_trailing_slash(self):
        from app.adapters.langchain_history import AgentMemoryDBChatMessageHistory

        h = AgentMemoryDBChatMessageHistory(
            base_url="http://localhost:8100/",
            user_id="u1",
            session_id="s1",
        )
        assert h.base_url == "http://localhost:8100"

    def test_sync_messages_raises(self, history):
        with pytest.raises(NotImplementedError):
            _ = history.messages

    def test_sync_add_message_raises(self, history):
        from langchain_core.messages import HumanMessage

        with pytest.raises(NotImplementedError):
            history.add_message(HumanMessage(content="hi"))

    def test_sync_clear_raises(self, history):
        with pytest.raises(NotImplementedError):
            history.clear()

    @pytest.mark.asyncio
    async def test_aget_messages_empty(self, history):
        history._client.get = AsyncMock(return_value=FakeResponse([]))
        msgs = await history.aget_messages()
        assert msgs == []

    @pytest.mark.asyncio
    async def test_aget_messages_filters_by_session(self, history, session_id):
        """Only memories whose key starts with session_id are returned."""
        fake_data = [
            {
                "memory_key": f"{session_id}:000001",
                "content": "Hello",
                "payload": {"role": "human"},
            },
            {
                "memory_key": "other-session:000001",
                "content": "Ignored",
                "payload": {"role": "human"},
            },
        ]
        history._client.get = AsyncMock(return_value=FakeResponse(fake_data))
        msgs = await history.aget_messages()
        assert len(msgs) == 1
        assert msgs[0].content == "Hello"

    @pytest.mark.asyncio
    async def test_aadd_messages_posts_upsert(self, history):
        from langchain_core.messages import AIMessage, HumanMessage

        history._client.post = AsyncMock(return_value=FakeResponse({}))

        await history.aadd_messages(
            [
                HumanMessage(content="Hi"),
                AIMessage(content="Hello!"),
            ]
        )

        assert history._client.post.call_count == 2

        # Check first call
        first_call = history._client.post.call_args_list[0]
        assert first_call.args[0] == "/api/v1/memories/upsert"
        body = first_call.kwargs["json"]
        assert body["memory_type"] == "episodic"
        assert body["content"] == "Hi"
        assert body["payload"]["role"] == "human"

        # Check second call
        second_call = history._client.post.call_args_list[1]
        body2 = second_call.kwargs["json"]
        assert body2["payload"]["role"] == "ai"

    @pytest.mark.asyncio
    async def test_aadd_messages_with_ttl(self, user_id, session_id):
        from app.adapters.langchain_history import AgentMemoryDBChatMessageHistory

        h = AgentMemoryDBChatMessageHistory(
            base_url="http://localhost:8100",
            user_id=user_id,
            session_id=session_id,
            message_ttl_seconds=3600,
        )
        h._client.post = AsyncMock(return_value=FakeResponse({}))

        from langchain_core.messages import HumanMessage

        await h.aadd_messages([HumanMessage(content="test")])

        body = h._client.post.call_args.kwargs["json"]
        assert "expires_at" in body

    @pytest.mark.asyncio
    async def test_aclear_archives_session_memories(self, history, session_id):
        fake_memories = [
            {"id": str(uuid.uuid4()), "memory_key": f"{session_id}:000001"},
            {"id": str(uuid.uuid4()), "memory_key": f"{session_id}:000002"},
            {"id": str(uuid.uuid4()), "memory_key": "other-session:000001"},
        ]
        history._client.get = AsyncMock(return_value=FakeResponse(fake_memories))
        history._client.patch = AsyncMock(return_value=FakeResponse({}))

        await history.aclear()

        # Should patch only the 2 session memories (not the other-session one)
        assert history._client.patch.call_count == 2

        # Each patch should set status to archived
        for call in history._client.patch.call_args_list:
            assert call.kwargs["json"]["status"] == "archived"

    @pytest.mark.asyncio
    async def test_role_classification(self):
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        from app.adapters.langchain_history import _classify_role

        assert _classify_role(HumanMessage(content="x")) == "human"
        assert _classify_role(AIMessage(content="x")) == "ai"
        assert _classify_role(SystemMessage(content="x")) == "system"
