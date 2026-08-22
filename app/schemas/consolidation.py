"""Consolidation schemas — reflection run records."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.schemas.common import OrmBase


class ConsolidationRunResponse(OrmBase):
    """One sleep-time consolidation pass.

    A ``skipped`` status with a ``skipped_reason`` is the normal, informative
    outcome when reflection has nothing to work with — it is not an error.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID | None = None
    kind: str
    status: str
    skipped_reason: str | None = None
    memories_considered: int
    clusters_found: int
    insights_created: int
    details: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int
    started_at: datetime
    finished_at: datetime | None = None
