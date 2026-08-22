"""Forgetting log — an audit trail for every memory removal.

Every forgetting decision is recorded: decay-driven archival, expiry, and hard
erasure (GDPR "right to be forgotten"). For erasures the content itself is gone,
so the row keeps a SHA-256 ``content_hash`` — that proves *what* was deleted
without retaining it, which is the whole point of auditable erasure.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ForgettingLog(Base):
    __tablename__ = "forgetting_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # No FK: the referenced memory may be hard-deleted — the tombstone outlives it.
    memory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # decayed_archive | expired | user_erasure | admin_erasure
    action: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # SHA-256 of the erased content — proves what was deleted without keeping it.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
