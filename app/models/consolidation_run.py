"""Consolidation run — an audit record for each sleep-time reflection pass.

Reflection is the one memory operation that *invents* content: it writes facts
nobody stated, inferred from a cluster of things that were. That deserves a
record of its own — what it looked at, what it produced, and, when it produced
nothing, exactly why. A run that skipped because no LLM was configured is a
different fact from a run that found nothing worth saying, and an operator
needs to be able to tell them apart without reading logs.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConsolidationRun(Base):
    __tablename__ = "consolidation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Kind of consolidation pass. "reflection" today; the table is shaped to
    # hold future passes (re-clustering, summarisation) without a migration.
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="reflection", index=True)
    # completed | skipped | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="completed", index=True)
    # Why a run produced nothing: disabled | no_llm_provider | too_few_memories |
    # no_clusters | dry_run. Empty on a completed run.
    skipped_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    memories_considered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clusters_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    insights_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Per-cluster detail: sizes, source memory ids, the insight key written.
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
