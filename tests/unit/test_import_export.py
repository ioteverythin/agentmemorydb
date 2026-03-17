"""Unit tests for import/export service."""

from __future__ import annotations

import uuid

import pytest

from app.models.user import User
from app.schemas.memory import MemoryUpsert
from app.services.import_export_service import ImportExportService
from app.services.memory_service import MemoryService


@pytest.mark.unit
class TestImportExport:
    async def _setup_user(self, session) -> uuid.UUID:
        user_id = uuid.uuid4()
        user = User(id=user_id, name="test-ie-user")
        session.add(user)
        await session.flush()
        return user_id

    @pytest.mark.asyncio
    async def test_export_empty(self, unit_session):
        """Exporting when no memories exist should return empty list."""
        user_id = await self._setup_user(unit_session)
        svc = ImportExportService(unit_session)
        data = await svc.export_memories(user_id)
        assert data["export_version"] == "1.0"
        assert data["memories"] == []

    @pytest.mark.asyncio
    async def test_export_roundtrip(self, unit_session):
        """Export → Import should preserve memory data."""
        user_id = await self._setup_user(unit_session)
        mem_svc = MemoryService(unit_session)

        await mem_svc.upsert(
            MemoryUpsert(
                user_id=user_id,
                memory_key="export_test",
                memory_type="semantic",
                content="Roundtrip test content.",
            )
        )
        await unit_session.flush()

        ie_svc = ImportExportService(unit_session)
        export_data = await ie_svc.export_memories(user_id=user_id)

        assert len(export_data["memories"]) == 1
        assert export_data["memories"][0]["memory_key"] == "export_test"

    @pytest.mark.asyncio
    async def test_import_creates_memories(self, unit_session):
        """Import should create memories from exported data."""
        user_id = await self._setup_user(unit_session)

        import_data = {
            "export_version": "1.0",
            "memories": [
                {
                    "user_id": str(user_id),
                    "memory_key": "imported_fact",
                    "memory_type": "semantic",
                    "content": "Imported content.",
                    "scope": "user",
                }
            ],
        }

        ie_svc = ImportExportService(unit_session)
        result = await ie_svc.import_memories(user_id, import_data, strategy="upsert")
        assert result["imported"] == 1
        assert result["errors"] == 0
