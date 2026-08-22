"""Sleep-time consolidation: a consolidation_runs audit table.

Reflection writes facts nobody stated, so each pass records what it considered,
what it produced, and — when it produced nothing — why. "Skipped because no LLM
was configured" and "found nothing worth saying" are different facts.

Revision ID: 010_consolidation_runs
Revises: 009_write_provenance
Create Date: 2026-08-19 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_consolidation_runs"
down_revision: Union[str, None] = "009_write_provenance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "consolidation_runs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("project_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="reflection"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="completed"),
        sa.Column("skipped_reason", sa.String(length=64), nullable=True),
        sa.Column("memories_considered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clusters_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("insights_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("details", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_consolidation_runs_user_id", "consolidation_runs", ["user_id"])
    op.create_index("ix_consolidation_runs_kind", "consolidation_runs", ["kind"])
    op.create_index("ix_consolidation_runs_status", "consolidation_runs", ["status"])
    op.create_index("ix_consolidation_runs_started_at", "consolidation_runs", ["started_at"])


def downgrade() -> None:
    op.drop_table("consolidation_runs")
