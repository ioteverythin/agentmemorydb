"""Forgetting schemas — audit-trail entries and erasure receipts."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import OrmBase


class ForgettingLogResponse(OrmBase):
    """One recorded forgetting decision.

    ``content_hash`` is present for erasures: the content is gone, the hash
    proves what was deleted.
    """

    id: uuid.UUID
    memory_id: uuid.UUID
    user_id: uuid.UUID
    action: str
    reason: str | None = None
    triggered_by: str | None = None
    content_hash: str | None = None
    occurred_at: datetime


class ErasureResponse(BaseModel):
    """Receipt for a hard erasure (GDPR right-to-be-forgotten)."""

    erased: int
    action: str
    memory_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
