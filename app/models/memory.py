"""Memory model — canonical, versioned memory records."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import Base


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Identity & scope ────────────────────────────────────────
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    memory_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="user", index=True)

    # ── Content ─────────────────────────────────────────────────
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    embedding = mapped_column(
        Vector(settings.embedding_dimension), nullable=True
    )
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Provenance ──────────────────────────────────────────────
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="system_inference")
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_observation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # ── Governance ──────────────────────────────────────────────
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    authority_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    importance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    recency_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    # ── Validity window ─────────────────────────────────────────
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Versioning ──────────────────────────────────────────────
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # ── Timestamps ──────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_memories_user_key", "user_id", "memory_key"),
        Index("ix_memories_scope_status", "scope", "status"),
        Index("ix_memories_payload_gin", "payload", postgresql_using="gin"),
        Index(
            "ix_memories_embedding_ivfflat",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": settings.vector_index_lists},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
