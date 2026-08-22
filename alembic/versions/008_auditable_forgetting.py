"""Auditable forgetting: pinned memories + a forgetting_log tombstone table.

  1. ``memories.pinned`` — exempt from importance decay and retention archival.
  2. ``forgetting_log`` — one row per forgetting decision (decayed_archive,
     expired, user_erasure, admin_erasure). Erasure rows keep only a SHA-256 of
     the deleted content, proving *what* was erased without retaining it.

Revision ID: 008_auditable_forgetting
Revises: 007_bitemporal_validity
Create Date: 2026-08-17 01:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_auditable_forgetting"
down_revision: Union[str, None] = "007_bitemporal_validity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "memories",
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_memories_pinned", "memories", ["pinned"])

    op.create_table(
        "forgetting_log",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        # Intentionally no FK — the tombstone must outlive a hard-deleted memory.
        sa.Column("memory_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.String(length=128), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_forgetting_log_memory_id", "forgetting_log", ["memory_id"])
    op.create_index("ix_forgetting_log_user_id", "forgetting_log", ["user_id"])
    op.create_index("ix_forgetting_log_action", "forgetting_log", ["action"])
    op.create_index("ix_forgetting_log_occurred_at", "forgetting_log", ["occurred_at"])


def downgrade() -> None:
    op.drop_table("forgetting_log")
    op.drop_index("ix_memories_pinned", table_name="memories")
    op.drop_column("memories", "pinned")
