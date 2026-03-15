"""Initial schema — all core tables, indexes, and pgvector extension.

Revision ID: 001_initial
Revises: None
Create Date: 2024-01-01 00:00:00.000000
"""
from __future__ import annotations

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Embedding dimension — read from env so it matches the configured provider
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIMENSION", "1536"))
VECTOR_INDEX_LISTS = 100


def upgrade() -> None:
    # ── Enable pgvector extension ───────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── users ───────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("external_id", sa.String(255), unique=True, nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("metadata", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_external_id", "users", ["external_id"])

    # ── projects ────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    # ── agent_runs ──────────────────────────────────────────────
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("agent_name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("context", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_runs_user_id", "agent_runs", ["user_id"])
    op.create_index("ix_agent_runs_project_id", "agent_runs", ["project_id"])

    # ── memories (before events/observations due to FK from observations) ──
    op.create_table(
        "memories",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("memory_key", sa.String(512), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False, server_default="user"),
        sa.Column("memory_type", sa.String(32), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("payload", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("source_type", sa.String(64), nullable=False, server_default="system_inference"),
        sa.Column("source_event_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_observation_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_run_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("authority_level", sa.Integer, nullable=False, server_default="1"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("importance_score", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("recency_score", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_memories_user_id", "memories", ["user_id"])
    op.create_index("ix_memories_project_id", "memories", ["project_id"])
    op.create_index("ix_memories_memory_key", "memories", ["memory_key"])
    op.create_index("ix_memories_scope", "memories", ["scope"])
    op.create_index("ix_memories_memory_type", "memories", ["memory_type"])
    op.create_index("ix_memories_status", "memories", ["status"])
    op.create_index("ix_memories_content_hash", "memories", ["content_hash"])
    op.create_index("ix_memories_user_key", "memories", ["user_id", "memory_key"])
    op.create_index("ix_memories_scope_status", "memories", ["scope", "status"])
    op.create_index(
        "ix_memories_payload_gin",
        "memories",
        ["payload"],
        postgresql_using="gin",
    )
    # pgvector IVFFlat index — requires data to exist; safe to create early
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_memories_embedding_ivfflat
        ON memories
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = {VECTOR_INDEX_LISTS})
        """
    )

    # ── events ──────────────────────────────────────────────────
    op.create_table(
        "events",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("payload", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("sequence_number", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_events_run_id", "events", ["run_id"])
    op.create_index("ix_events_event_type", "events", ["event_type"])
    op.create_index("ix_events_run_created", "events", ["run_id", "created_at"])
    op.create_index(
        "ix_events_payload_gin",
        "events",
        ["payload"],
        postgresql_using="gin",
    )

    # ── observations ────────────────────────────────────────────
    op.create_table(
        "observations",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("observation_type", sa.String(64), nullable=True),
        sa.Column("source_type", sa.String(64), nullable=False, server_default="system_inference"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("metadata", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column(
            "memory_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_observations_event_id", "observations", ["event_id"])
    op.create_index("ix_observations_run_id", "observations", ["run_id"])

    # ── memory_versions ─────────────────────────────────────────
    op.create_table(
        "memory_versions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "memory_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("importance_score", sa.Float, nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("superseded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_memory_versions_memory_id", "memory_versions", ["memory_id"])

    # ── memory_links ────────────────────────────────────────────
    op.create_table(
        "memory_links",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_memory_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_memory_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("link_type", sa.String(32), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_memory_links_source", "memory_links", ["source_memory_id"])
    op.create_index("ix_memory_links_target", "memory_links", ["target_memory_id"])
    op.create_index("ix_memory_links_link_type", "memory_links", ["link_type"])

    # ── tasks ───────────────────────────────────────────────────
    op.create_table(
        "tasks",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("state", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer, nullable=True, server_default="0"),
        sa.Column("context", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("result", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tasks_run_id", "tasks", ["run_id"])
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"])
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
    op.create_index("ix_tasks_state", "tasks", ["state"])

    # ── task_state_transitions ──────────────────────────────────
    op.create_table(
        "task_state_transitions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_state", sa.String(32), nullable=False),
        sa.Column("to_state", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("triggered_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_task_transitions_task_id", "task_state_transitions", ["task_id"])

    # ── retrieval_logs ──────────────────────────────────────────
    op.create_table(
        "retrieval_logs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("strategy", sa.String(64), nullable=False, server_default="hybrid"),
        sa.Column("filters_json", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("query_text", sa.Text, nullable=True),
        sa.Column("top_k", sa.Integer, nullable=False, server_default="10"),
        sa.Column("total_candidates", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_retrieval_logs_run_id", "retrieval_logs", ["run_id"])

    # ── retrieval_log_items ─────────────────────────────────────
    op.create_table(
        "retrieval_log_items",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "retrieval_log_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("retrieval_logs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "memory_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("final_score", sa.Float, nullable=False),
        sa.Column("vector_score", sa.Float, nullable=True),
        sa.Column("recency_score", sa.Float, nullable=True),
        sa.Column("importance_score", sa.Float, nullable=True),
        sa.Column("authority_score", sa.Float, nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("selected_for_prompt", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_retrieval_log_items_log_id", "retrieval_log_items", ["retrieval_log_id"])

    # ── artifacts_metadata ──────────────────────────────────────
    op.create_table(
        "artifacts_metadata",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("uri", sa.String(2048), nullable=True),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("size_bytes", sa.BigInteger, nullable=True),
        sa.Column("checksum", sa.String(128), nullable=True),
        sa.Column("metadata", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_artifacts_run_id", "artifacts_metadata", ["run_id"])


def downgrade() -> None:
    op.drop_table("artifacts_metadata")
    op.drop_table("retrieval_log_items")
    op.drop_table("retrieval_logs")
    op.drop_table("task_state_transitions")
    op.drop_table("tasks")
    op.drop_table("memory_links")
    op.drop_table("memory_versions")
    op.drop_table("observations")
    op.drop_table("events")
    op.drop_table("memories")
    op.drop_table("agent_runs")
    op.drop_table("projects")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS vector")
