"""Bitemporal fact validity: enforce valid_from, add supersession pointer + indexes.

``valid_from`` / ``valid_to`` already existed (nullable) and were already
honoured by retrieval. This migration makes the world-validity dimension
first-class:

  1. Backfill ``valid_from`` from ``created_at`` and make it NOT NULL DEFAULT now().
  2. Add ``superseded_by`` — set only when a *different* canonical row replaces
     this one (in-place supersession is recorded via the version chain).
  3. Partial index for current-fact lookup (``WHERE valid_to IS NULL``) and a
     composite index for as-of range scans.

Revision ID: 007_bitemporal_validity
Revises: 006_teams_acl_sharing
Create Date: 2026-08-17 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_bitemporal_validity"
down_revision: Union[str, None] = "006_teams_acl_sharing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Backfill then tighten valid_from.
    op.execute(
        "UPDATE memories SET valid_from = COALESCE(valid_from, created_at, now()) "
        "WHERE valid_from IS NULL"
    )
    op.alter_column(
        "memories",
        "valid_from",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    # 2. Supersession pointer (cross-row replacement only).
    op.add_column(
        "memories",
        sa.Column("superseded_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_memories_superseded_by",
        "memories",
        "memories",
        ["superseded_by"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3. Temporal indexes.
    op.create_index(
        "ix_memories_current",
        "memories",
        ["user_id", "memory_key"],
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index(
        "ix_memories_user_validity", "memories", ["user_id", "valid_from", "valid_to"]
    )


def downgrade() -> None:
    op.drop_index("ix_memories_user_validity", table_name="memories")
    op.drop_index("ix_memories_current", table_name="memories")
    op.drop_constraint("fk_memories_superseded_by", "memories", type_="foreignkey")
    op.drop_column("memories", "superseded_by")
    op.alter_column(
        "memories",
        "valid_from",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        server_default=None,
    )
