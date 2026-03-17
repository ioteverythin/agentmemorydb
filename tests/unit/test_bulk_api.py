"""Unit tests for bulk API schemas and validation."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.api.v1.bulk import BatchSearchRequest, BatchUpsertRequest


@pytest.mark.unit
class TestBulkSchemas:
    def test_batch_upsert_max_100(self):
        """BatchUpsertRequest should reject more than 100 items."""
        # Build 101 minimal upsert payloads
        from app.schemas.memory import MemoryUpsert

        items = [
            MemoryUpsert(
                user_id=uuid.uuid4(),
                memory_key=f"k_{i}",
                memory_type="semantic",
                content=f"content {i}",
            )
            for i in range(101)
        ]
        with pytest.raises(ValidationError):
            BatchUpsertRequest(memories=items)

    def test_batch_upsert_accepts_100(self):
        from app.schemas.memory import MemoryUpsert

        items = [
            MemoryUpsert(
                user_id=uuid.uuid4(),
                memory_key=f"k_{i}",
                memory_type="semantic",
                content=f"content {i}",
            )
            for i in range(100)
        ]
        req = BatchUpsertRequest(memories=items)
        assert len(req.memories) == 100

    def test_batch_search_max_20(self):
        from app.schemas.memory import MemorySearchRequest

        queries = [MemorySearchRequest(user_id=uuid.uuid4(), query_text=f"q{i}") for i in range(21)]
        with pytest.raises(ValidationError):
            BatchSearchRequest(queries=queries)
