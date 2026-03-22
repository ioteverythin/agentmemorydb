"""Switch default vector index from IVFFlat to HNSW.

HNSW (Hierarchical Navigable Small World) delivers ~15x better QPS vs
IVFFlat at equivalent recall, requires no training step, and handles
incremental inserts better.  The pgvector maintainers now recommend it as
the default index strategy.

This migration:
  1. Drops the existing IVFFlat index (if present).
  2. Creates an HNSW index CONCURRENTLY (table stays fully online).

Run with:
    alembic upgrade head

Rollback with:
    alembic downgrade 003_data_masking

Revision ID: 004_hnsw_index
Revises: 003_data_masking
Create Date: 2026-03-22 00:00:00.000000
"""

from __future__ import annotations

import os
from typing import Sequence, Union

from alembic import op

revision: str = "004_hnsw_index"
down_revision: Union[str, None] = "003_data_masking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# HNSW tunables — read from environment so operators can override at deploy time.
HNSW_M = int(os.environ.get("HNSW_M", "16"))
HNSW_EF_CONSTRUCTION = int(os.environ.get("HNSW_EF_CONSTRUCTION", "64"))

# IVFFlat settings for rollback
VECTOR_INDEX_LISTS = int(os.environ.get("VECTOR_INDEX_LISTS", "100"))


def upgrade() -> None:
    """Replace IVFFlat with HNSW index (CONCURRENTLY = zero-downtime)."""

    # Drop existing IVFFlat index
    op.execute("DROP INDEX IF EXISTS ix_memories_embedding_ivfflat")

    # Create HNSW index CONCURRENTLY — requires running outside a
    # transaction block.  Alembic's --transaction-per-migration flag
    # must be disabled, or call op.execute() with execution_options.
    op.execute(
        f"""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_memories_embedding_hnsw
        ON memories
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = {HNSW_M}, ef_construction = {HNSW_EF_CONSTRUCTION})
        """
    )


def downgrade() -> None:
    """Revert to IVFFlat index."""

    op.execute("DROP INDEX IF EXISTS ix_memories_embedding_hnsw")

    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_memories_embedding_ivfflat
        ON memories
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = {VECTOR_INDEX_LISTS})
        """
    )
