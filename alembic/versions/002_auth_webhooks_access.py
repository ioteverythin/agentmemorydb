"""New tables: api_keys, webhooks, webhook_deliveries, memory_access_logs + tsvector.

Revision ID: 002_auth_webhooks_access
Revises: 001_initial
Create Date: 2026-02-24 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_auth_webhooks_access"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── api_keys ────────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("key_prefix", sa.String(12), nullable=False),
        sa.Column("scopes", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)

    # ── webhooks ────────────────────────────────────────────────
    op.create_table(
        "webhooks",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("secret", sa.String(255), nullable=True),
        sa.Column("events", sa.Text, nullable=False, server_default="*"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("max_retries", sa.Integer, nullable=False, server_default="3"),
        sa.Column("metadata", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_webhooks_user_id", "webhooks", ["user_id"])

    # ── webhook_deliveries ──────────────────────────────────────
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "webhook_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("webhooks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("response_body", sa.Text, nullable=True),
        sa.Column("success", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("attempt", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_webhook_deliveries_webhook_id", "webhook_deliveries", ["webhook_id"])

    # ── memory_access_logs ──────────────────────────────────────
    op.create_table(
        "memory_access_logs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "memory_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("access_type", sa.String(32), nullable=False, server_default="retrieval"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_memory_access_logs_memory_id", "memory_access_logs", ["memory_id"])
    op.create_index("ix_memory_access_logs_user_id", "memory_access_logs", ["user_id"])
    op.create_index(
        "ix_memory_access_logs_created", "memory_access_logs", ["created_at"]
    )

    # ── Add tsvector column to memories for full-text search ────
    op.add_column(
        "memories",
        sa.Column("search_vector", sa.dialects.postgresql.TSVECTOR, nullable=True),
    )
    op.create_index(
        "ix_memories_search_vector_gin",
        "memories",
        ["search_vector"],
        postgresql_using="gin",
    )

    # Create trigger to auto-update search_vector on insert/update
    op.execute(
        """
        CREATE OR REPLACE FUNCTION memories_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := to_tsvector('english', COALESCE(NEW.content, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER memories_search_vector_trigger
        BEFORE INSERT OR UPDATE OF content ON memories
        FOR EACH ROW EXECUTE FUNCTION memories_search_vector_update();
        """
    )

    # Backfill existing rows
    op.execute(
        """
        UPDATE memories SET search_vector = to_tsvector('english', COALESCE(content, ''));
        """
    )

    # ── Add access_count column to memories for quick access ────
    op.add_column(
        "memories",
        sa.Column("access_count", sa.Integer, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("memories", "access_count")
    op.execute("DROP TRIGGER IF EXISTS memories_search_vector_trigger ON memories")
    op.execute("DROP FUNCTION IF EXISTS memories_search_vector_update()")
    op.drop_index("ix_memories_search_vector_gin", table_name="memories")
    op.drop_column("memories", "search_vector")
    op.drop_table("memory_access_logs")
    op.drop_table("webhook_deliveries")
    op.drop_table("webhooks")
    op.drop_table("api_keys")
