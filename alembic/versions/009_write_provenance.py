"""Write provenance: origin + origin_ref on memories and observations.

``origin`` records *who* wrote a fact — the trust domain it entered from —
which is what the authority ceiling and quarantine rules key off. It is
deliberately separate from ``source_type`` (what kind of statement it is).

Existing rows are backfilled to ``agent_inference``, the default for an
unattributed write, so behaviour is unchanged until the feature flag is on.

Revision ID: 009_write_provenance
Revises: 008_auditable_forgetting
Create Date: 2026-08-18 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_write_provenance"
down_revision: Union[str, None] = "008_auditable_forgetting"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("memories", "observations"):
        op.add_column(
            table,
            sa.Column(
                "origin",
                sa.String(length=32),
                nullable=False,
                server_default="agent_inference",
            ),
        )
        op.add_column(table, sa.Column("origin_ref", sa.String(length=512), nullable=True))
        op.create_index(f"ix_{table}_origin", table, ["origin"])

    # Quarantined memories are looked up as a review queue: owner + status.
    op.create_index(
        "ix_memories_quarantine",
        "memories",
        ["user_id", "status"],
        postgresql_where=sa.text("status = 'quarantined'"),
    )


def downgrade() -> None:
    op.drop_index("ix_memories_quarantine", table_name="memories")
    for table in ("memories", "observations"):
        op.drop_index(f"ix_{table}_origin", table_name=table)
        op.drop_column(table, "origin_ref")
        op.drop_column(table, "origin")
