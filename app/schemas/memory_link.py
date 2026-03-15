"""MemoryLink schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import OrmBase


class MemoryLinkCreate(BaseModel):
    source_memory_id: uuid.UUID
    target_memory_id: uuid.UUID
    link_type: str  # LinkType value
    description: str | None = None


class MemoryLinkResponse(OrmBase):
    id: uuid.UUID
    source_memory_id: uuid.UUID
    target_memory_id: uuid.UUID
    link_type: str
    description: str | None = None
    created_at: datetime
