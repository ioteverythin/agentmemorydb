"""Automatic memory linking: composite indexes for edge deduplication.

Autolinking checks, on every write, whether an edge already exists between two
memories — in *either* direction, since ``related_to`` is symmetric. That query
filters on ``link_type`` and matches either endpoint, so the existing
single-column indexes on ``source_memory_id`` / ``target_memory_id`` each force a
filter step. Two composite indexes let both halves of the OR be index-only.

No unique constraint: existing deployments may already hold duplicate manual
links, and a migration that fails on real data is worse than one that leaves
deduplication to the writer.

Revision ID: 011_autolink_indexes
Revises: 010_consolidation_runs
Create Date: 2026-08-20 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "011_autolink_indexes"
down_revision: Union[str, None] = "010_consolidation_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_memory_links_type_source",
        "memory_links",
        ["link_type", "source_memory_id"],
    )
    op.create_index(
        "ix_memory_links_type_target",
        "memory_links",
        ["link_type", "target_memory_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_memory_links_type_target", table_name="memory_links")
    op.drop_index("ix_memory_links_type_source", table_name="memory_links")
