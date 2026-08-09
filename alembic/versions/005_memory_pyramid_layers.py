"""Add memory-pyramid layer + lossless version-snapshot columns.

Adds:
  1. ``memories.layer`` — the distillation layer (raw/atom/scenario/persona)
     with a partial index for layer-filtered retrieval.
  2. Governance/validity columns on ``memory_versions`` so a prior version can
     be restored faithfully (memory_type, scope, layer, authority_level, and
     the validity window). Existing rows keep NULLs; new snapshots populate them.

Revision ID: 005_memory_pyramid_layers
Revises: 004_hnsw_index
Create Date: 2026-08-09 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_memory_pyramid_layers"
down_revision: Union[str, None] = "004_hnsw_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # memories.layer — default existing rows to 'atom' (single extracted fact).
    op.add_column(
        "memories",
        sa.Column("layer", sa.String(length=16), nullable=False, server_default="atom"),
    )
    op.create_index("ix_memories_layer", "memories", ["layer"])

    # memory_versions: faithful-rollback snapshot columns (nullable for history).
    op.add_column("memory_versions", sa.Column("memory_type", sa.String(length=32), nullable=True))
    op.add_column("memory_versions", sa.Column("scope", sa.String(length=32), nullable=True))
    op.add_column("memory_versions", sa.Column("layer", sa.String(length=16), nullable=True))
    op.add_column("memory_versions", sa.Column("authority_level", sa.Integer(), nullable=True))
    op.add_column(
        "memory_versions", sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "memory_versions", sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "memory_versions", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("memory_versions", "expires_at")
    op.drop_column("memory_versions", "valid_to")
    op.drop_column("memory_versions", "valid_from")
    op.drop_column("memory_versions", "authority_level")
    op.drop_column("memory_versions", "layer")
    op.drop_column("memory_versions", "scope")
    op.drop_column("memory_versions", "memory_type")

    op.drop_index("ix_memories_layer", table_name="memories")
    op.drop_column("memories", "layer")
