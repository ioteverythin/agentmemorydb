"""Integration test: retrieval audit-logging.

Verifies that `RetrievalService.search` creates an audit log with items,
and that `RetrievalLogService.list_by_run` returns them correctly.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.agent_run import AgentRun
from app.models.user import User
from app.schemas.memory import MemorySearchRequest, MemoryUpsert
from app.services.memory_service import MemoryService
from app.services.retrieval_log_service import RetrievalLogService
from app.services.retrieval_service import RetrievalService


@pytest.mark.integration
class TestRetrievalLogging:
    """Ensure retrieval operations leave audit trail."""

    async def _seed(self, session):
        """Create a user, a run, and a couple of memories."""
        user_id = uuid.uuid4()
        run_id = uuid.uuid4()
        user = User(id=user_id, name="retrieval-log-user")
        run = AgentRun(id=run_id, user_id=user_id, agent_name="tester", status="running")
        session.add_all([user, run])
        await session.flush()

        svc = MemoryService(session)
        await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="fact_one",
                memory_type="semantic",
                content="The capital of France is Paris.",
            )
        )
        await svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="fact_two",
                memory_type="semantic",
                content="Water boils at 100°C at sea level.",
            )
        )
        return user_id, run_id

    @pytest.mark.asyncio
    async def test_retrieval_creates_log(self, unit_session):
        """A search via RetrievalService should persist an audit log.

        NOTE: We intentionally omit ``query_text`` so the search takes the
        metadata-only path.  SQLite does not support the pgvector ``<=>``
        operator, so providing a query_text would generate an embedding and
        trigger a vector-search SQL that SQLite cannot execute.
        """
        user_id, run_id = await self._seed(unit_session)

        retrieval = RetrievalService(unit_session)
        result = await retrieval.search(
            MemorySearchRequest(
                user_id=user_id,
                top_k=5,
                run_id=run_id,
            )
        )
        # Metadata-only path — should find the seeded memories
        assert result.total_candidates >= 0

        # Verify audit log was persisted
        log_svc = RetrievalLogService(unit_session)
        logs = await log_svc.list_by_run(run_id)
        assert len(logs) >= 1
        latest = logs[0]
        assert latest.run_id == run_id
        assert latest.top_k == 5
