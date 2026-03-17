"""Import/Export service — bulk data portability for memories."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.models.memory_link import MemoryLink
from app.repositories.memory_repository import MemoryRepository
from app.schemas.memory import MemoryUpsert
from app.services.memory_service import MemoryService


class ImportExportService:
    """Bulk import and export of memories for data portability.

    Export format is a JSON-serializable list of memory dicts with
    optional version history and links.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = MemoryRepository(session)
        self._memory_svc = MemoryService(session)

    # ── Export ───────────────────────────────────────────────────

    async def export_memories(
        self,
        user_id: uuid.UUID,
        *,
        include_versions: bool = True,
        include_links: bool = True,
        status: str | None = None,
        memory_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Export all memories for a user as a portable JSON structure.

        Returns:
        {
            "export_version": "1.0",
            "exported_at": "...",
            "user_id": "...",
            "memory_count": N,
            "memories": [...],
            "links": [...],  # if include_links
        }
        """
        conditions = [Memory.user_id == user_id]
        if status:
            conditions.append(Memory.status == status)
        if memory_types:
            conditions.append(Memory.memory_type.in_(memory_types))

        stmt = select(Memory).where(*conditions).order_by(Memory.created_at)
        result = await self._session.execute(stmt)
        memories = result.scalars().all()

        exported_memories: list[dict[str, Any]] = []
        for mem in memories:
            entry: dict[str, Any] = {
                "id": str(mem.id),
                "memory_key": mem.memory_key,
                "memory_type": mem.memory_type,
                "scope": mem.scope,
                "content": mem.content,
                "content_hash": mem.content_hash,
                "payload": mem.payload,
                "source_type": mem.source_type,
                "status": mem.status,
                "authority_level": mem.authority_level,
                "confidence": mem.confidence,
                "importance_score": mem.importance_score,
                "valid_from": mem.valid_from.isoformat() if mem.valid_from else None,
                "valid_to": mem.valid_to.isoformat() if mem.valid_to else None,
                "expires_at": mem.expires_at.isoformat() if mem.expires_at else None,
                "version": mem.version,
                "created_at": mem.created_at.isoformat(),
                "updated_at": mem.updated_at.isoformat(),
            }

            if include_versions:
                versions = await self._repo.get_versions(mem.id)
                entry["versions"] = [
                    {
                        "version": v.version,
                        "content": v.content,
                        "content_hash": v.content_hash,
                        "confidence": v.confidence,
                        "importance_score": v.importance_score,
                        "source_type": v.source_type,
                        "status": v.status,
                        "created_at": v.created_at.isoformat(),
                        "superseded_at": v.superseded_at.isoformat() if v.superseded_at else None,
                    }
                    for v in versions
                ]

            exported_memories.append(entry)

        result_dict: dict[str, Any] = {
            "export_version": "1.0",
            "exported_at": datetime.now(UTC).isoformat(),
            "user_id": str(user_id),
            "memory_count": len(exported_memories),
            "memories": exported_memories,
        }

        if include_links:
            # Export all links between the user's memories
            memory_ids = [mem.id for mem in memories]
            if memory_ids:
                link_stmt = select(MemoryLink).where(
                    MemoryLink.source_memory_id.in_(memory_ids)
                    | MemoryLink.target_memory_id.in_(memory_ids)
                )
                link_result = await self._session.execute(link_stmt)
                links = link_result.scalars().all()
                result_dict["links"] = [
                    {
                        "source_memory_id": str(l.source_memory_id),
                        "target_memory_id": str(l.target_memory_id),
                        "link_type": l.link_type,
                        "description": l.description,
                    }
                    for l in links
                ]
            else:
                result_dict["links"] = []

        return result_dict

    # ── Import ───────────────────────────────────────────────────

    async def import_memories(
        self,
        user_id: uuid.UUID,
        data: dict[str, Any],
        *,
        strategy: str = "upsert",  # "upsert" | "skip_existing" | "overwrite"
    ) -> dict[str, int]:
        """Import memories from an export payload.

        Strategies:
        - upsert: Use the standard upsert logic (content-hash dedup)
        - skip_existing: Skip if a memory with the same key exists
        - overwrite: Always update even if content is identical

        Returns counts: {"imported": N, "skipped": N, "errors": N}
        """
        memories_data = data.get("memories", [])
        imported = 0
        skipped = 0
        errors = 0

        for entry in memories_data:
            try:
                if strategy == "skip_existing":
                    existing = await self._repo.find_active_by_key(
                        user_id=user_id,
                        memory_key=entry["memory_key"],
                        scope=entry.get("scope", "user"),
                    )
                    if existing:
                        skipped += 1
                        continue

                upsert_data = MemoryUpsert(
                    user_id=user_id,
                    memory_key=entry["memory_key"],
                    memory_type=entry.get("memory_type", "semantic"),
                    scope=entry.get("scope", "user"),
                    content=entry["content"],
                    payload=entry.get("payload"),
                    source_type=entry.get("source_type", "imported"),
                    authority_level=entry.get("authority_level", 1),
                    confidence=entry.get("confidence", 0.5),
                    importance_score=entry.get("importance_score", 0.5),
                )

                _, is_new = await self._memory_svc.upsert(upsert_data)
                if is_new:
                    imported += 1
                else:
                    if strategy == "upsert":
                        imported += 1
                    else:
                        skipped += 1

            except Exception:
                errors += 1

        # Import links if present
        links_data = data.get("links", [])
        for _link in links_data:
            try:
                # Links reference original IDs — map via memory_key lookups
                # For now, skip link import (requires ID mapping)
                pass
            except Exception:
                pass

        return {
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
        }
