"""Memory model — canonical, versioned memory records."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import Base


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Identity & scope ────────────────────────────────────────
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    memory_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="user", index=True)

    # ── Sharing / access control ────────────────────────────────
    # Visibility governs who (besides the owner) may read this memory.
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, default="private", index=True
    )
    # Team this memory belongs to when shared (team/restricted/agent visibility).
    team_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    # Bound agent identifier when visibility == "agent" (an agent "loadout").
    agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # ── Content ─────────────────────────────────────────────────
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # Distillation layer in the memory pyramid (raw/atom/scenario/persona).
    layer: Mapped[str] = mapped_column(String(16), nullable=False, default="atom", index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    embedding = mapped_column(Vector(settings.embedding_dimension), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Provenance ──────────────────────────────────────────────
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="system_inference")
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_observation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # ── Governance ──────────────────────────────────────────────
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    authority_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    importance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    recency_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    # ── Validity window (world time — see docs/temporal-model.md) ─
    # ``valid_from``/``valid_to`` bound when the fact was true *in the world*.
    # ``valid_to IS NULL`` marks the currently-valid generation. Prior
    # generations live in ``memory_versions`` with closed windows, so the
    # canonical row keeps a stable id across supersessions.
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set only when a *different* canonical row replaces this one (key rename
    # or an explicit replacement); in-place supersession uses the version chain.
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memories.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Versioning ──────────────────────────────────────────────
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # ── Timestamps ──────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @staticmethod
    def _build_vector_index() -> Index:
        """Build the vector index based on configuration.

        HNSW is the default — better QPS vs IVFFlat at equivalent recall,
        no training step, and handles incremental inserts better.
        """
        if settings.vector_index_type.lower() == "hnsw":
            return Index(
                "ix_memories_embedding_hnsw",
                "embedding",
                postgresql_using="hnsw",
                postgresql_with={
                    "m": settings.hnsw_m,
                    "ef_construction": settings.hnsw_ef_construction,
                },
                postgresql_ops={"embedding": "vector_cosine_ops"},
            )
        # Fallback: IVFFlat
        return Index(
            "ix_memories_embedding_ivfflat",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": settings.vector_index_lists},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        )

    __table_args__ = (
        Index("ix_memories_user_key", "user_id", "memory_key"),
        Index("ix_memories_scope_status", "scope", "status"),
        Index("ix_memories_payload_gin", "payload", postgresql_using="gin"),
        # Fast current-fact lookup: the hot path for upsert and default search.
        Index(
            "ix_memories_current",
            "user_id",
            "memory_key",
            postgresql_where=text("valid_to IS NULL"),
        ),
        # As-of range scans.
        Index("ix_memories_user_validity", "user_id", "valid_from", "valid_to"),
        _build_vector_index.__func__(),  # type: ignore[attr-defined]
    )
