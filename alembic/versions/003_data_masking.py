"""Add masking_logs table for data masking audit trail.

Revision ID: 003_data_masking
Revises: 002_auth_webhooks_access
Create Date: 2026-02-27 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_data_masking"
down_revision: Union[str, None] = "002_auth_webhooks_access"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "masking_logs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_name", sa.String(64), nullable=False),
        sa.Column("patterns_detected", sa.dialects.postgresql.JSONB, nullable=False),
        sa.Column("detection_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("original_content_hash", sa.String(128), nullable=True),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("run_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_masking_logs_entity_type", "masking_logs", ["entity_type"])
    op.create_index("ix_masking_logs_entity_id", "masking_logs", ["entity_id"])
    op.create_index("ix_masking_logs_user_id", "masking_logs", ["user_id"])
    op.create_index(
        "ix_masking_logs_created_at",
        "masking_logs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_masking_logs_created_at", table_name="masking_logs")
    op.drop_index("ix_masking_logs_user_id", table_name="masking_logs")
    op.drop_index("ix_masking_logs_entity_id", table_name="masking_logs")
    op.drop_index("ix_masking_logs_entity_type", table_name="masking_logs")
    op.drop_table("masking_logs")
