"""Masking audit log model — records every PII detection + masking action."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MaskingLog(Base):
    """Immutable audit record of a data-masking action.

    One row is created for each *field* that was masked within a single
    write operation.  The ``detections`` JSONB column stores pattern
    names and token counts (never the original PII).
    """

    __tablename__ = "masking_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # What entity was masked
    entity_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # memory | event | observation
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # content | payload.* | metadata.*

    # What was detected (no raw PII stored)
    patterns_detected: Mapped[list] = mapped_column(JSONB, nullable=False)  # ["email", "phone"]
    detection_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Hash of original content (for forensic correlation without storing PII)
    original_content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Context
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
