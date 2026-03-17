"""Masking service — orchestrates PII detection, replacement, and audit logging.

This service is the single integration point for the data pipeline.
Services call :meth:`mask_content` before persisting any text field;
it returns the masked text and (optionally) writes an audit log entry.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.models.masking_log import MaskingLog
from app.utils.hashing import compute_content_hash
from app.utils.masking import MaskingResult, PIIMaskingEngine, get_default_engine


class MaskingService:
    """Stateful service wrapping the masking engine + audit persistence."""

    def __init__(self, session: AsyncSession, engine: PIIMaskingEngine | None = None) -> None:
        self._session = session
        self._engine = engine or get_default_engine()

    @property
    def is_enabled(self) -> bool:
        return settings.enable_data_masking and bool(self._engine.active_patterns)

    # ── Public API ──────────────────────────────────────────────

    async def mask_content(
        self,
        text: str | None,
        *,
        entity_type: str,
        entity_id: uuid.UUID | None = None,
        field_name: str = "content",
        user_id: uuid.UUID | None = None,
        run_id: uuid.UUID | None = None,
    ) -> str | None:
        """Mask PII in *text* and optionally log the action.

        Returns the masked string (or the original if masking is disabled
        or nothing was detected).
        """
        if not text or not self.is_enabled:
            return text

        result = self._engine.mask_text(text)
        if not result.was_modified:
            return text

        # Audit log
        if settings.masking_log_detections:
            await self._write_log(
                entity_type=entity_type,
                entity_id=entity_id or uuid.uuid4(),
                field_name=field_name,
                result=result,
                user_id=user_id,
                run_id=run_id,
            )

        return result.masked_text

    async def mask_payload(
        self,
        payload: dict[str, Any] | None,
        *,
        entity_type: str,
        entity_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        run_id: uuid.UUID | None = None,
    ) -> dict[str, Any] | None:
        """Scan and mask all string values in a JSONB payload dict."""
        if not payload or not self.is_enabled:
            return payload

        detections = self._engine.mask_dict(payload)

        if detections and settings.masking_log_detections:
            for field_name, dets in detections.items():
                await self._write_log(
                    entity_type=entity_type,
                    entity_id=entity_id or uuid.uuid4(),
                    field_name=f"payload.{field_name}",
                    result=MaskingResult(
                        original_text="",
                        masked_text="",
                        detections=dets,
                        was_modified=True,
                    ),
                    user_id=user_id,
                    run_id=run_id,
                )

        return payload

    def mask_text_sync(self, text: str | None) -> str | None:
        """Non-async mask — for places where we can't await (e.g. validators).

        Does NOT write an audit log.
        """
        if not text or not self.is_enabled:
            return text
        result = self._engine.mask_text(text)
        return result.masked_text if result.was_modified else text

    # ── Audit log queries ───────────────────────────────────────

    async def list_logs(
        self,
        *,
        entity_type: str | None = None,
        user_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MaskingLog]:
        """Query masking audit logs with optional filters."""
        from sqlalchemy import select

        stmt = select(MaskingLog).order_by(MaskingLog.created_at.desc())
        if entity_type:
            stmt = stmt.where(MaskingLog.entity_type == entity_type)
        if user_id:
            stmt = stmt.where(MaskingLog.user_id == user_id)
        stmt = stmt.limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_stats(self) -> dict[str, Any]:
        """Aggregate masking statistics."""
        from sqlalchemy import func, select

        total_q = select(func.count(MaskingLog.id))
        total = (await self._session.execute(total_q)).scalar() or 0

        by_type_q = select(MaskingLog.entity_type, func.count(MaskingLog.id)).group_by(
            MaskingLog.entity_type
        )
        by_type_rows = (await self._session.execute(by_type_q)).all()
        by_entity_type = {row[0]: row[1] for row in by_type_rows}

        return {
            "total_masking_actions": total,
            "by_entity_type": by_entity_type,
            "masking_enabled": settings.enable_data_masking,
            "active_patterns": self._engine.active_patterns,
        }

    # ── Internal ────────────────────────────────────────────────

    async def _write_log(
        self,
        *,
        entity_type: str,
        entity_id: uuid.UUID,
        field_name: str,
        result: MaskingResult,
        user_id: uuid.UUID | None,
        run_id: uuid.UUID | None,
    ) -> MaskingLog:
        log = MaskingLog(
            entity_type=entity_type,
            entity_id=entity_id,
            field_name=field_name,
            patterns_detected=list({d.pattern_name for d in result.detections}),
            detection_count=len(result.detections),
            original_content_hash=compute_content_hash(result.original_text)
            if result.original_text
            else None,
            user_id=user_id,
            run_id=run_id,
        )
        self._session.add(log)
        return log
