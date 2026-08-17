"""Teams, ACL, and memory sharing (visibility / team_id / agent binding).

Adds the control plane for shared team memory:
  1. ``teams`` and ``team_memberships`` tables.
  2. ``memory_acls`` table for restricted-visibility grants.
  3. ``memories.visibility`` / ``team_id`` / ``agent_id`` columns.

Revision ID: 006_teams_acl_sharing
Revises: 005_memory_pyramid_layers
Create Date: 2026-08-16 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_teams_acl_sharing"
down_revision: Union[str, None] = "005_memory_pyramid_layers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "owner_user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_teams_owner_user_id", "teams", ["owner_user_id"])

    op.create_table(
        "team_memberships",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "team_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_member"),
    )
    op.create_index("ix_team_memberships_team_id", "team_memberships", ["team_id"])
    op.create_index("ix_team_memberships_user_id", "team_memberships", ["user_id"])

    op.create_table(
        "memory_acls",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "memory_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("principal_type", sa.String(length=16), nullable=False),
        sa.Column("principal_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "memory_id", "principal_type", "principal_id", name="uq_memory_acl_principal"
        ),
    )
    op.create_index("ix_memory_acls_memory_id", "memory_acls", ["memory_id"])
    op.create_index("ix_memory_acls_principal_id", "memory_acls", ["principal_id"])

    op.add_column(
        "memories",
        sa.Column("visibility", sa.String(length=16), nullable=False, server_default="private"),
    )
    op.add_column(
        "memories", sa.Column("team_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("memories", sa.Column("agent_id", sa.String(length=128), nullable=True))
    op.create_index("ix_memories_visibility", "memories", ["visibility"])
    op.create_index("ix_memories_team_id", "memories", ["team_id"])
    op.create_index("ix_memories_agent_id", "memories", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_memories_agent_id", table_name="memories")
    op.drop_index("ix_memories_team_id", table_name="memories")
    op.drop_index("ix_memories_visibility", table_name="memories")
    op.drop_column("memories", "agent_id")
    op.drop_column("memories", "team_id")
    op.drop_column("memories", "visibility")

    op.drop_table("memory_acls")
    op.drop_table("team_memberships")
    op.drop_table("teams")
