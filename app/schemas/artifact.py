"""Artifact schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.common import OrmBase


class ArtifactCreate(BaseModel):
    run_id: uuid.UUID | None = None
    user_id: uuid.UUID
    project_id: uuid.UUID | None = None
    artifact_type: str
    name: str
    uri: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    checksum: str | None = None
    metadata: dict[str, Any] | None = None


class ArtifactResponse(OrmBase):
    id: uuid.UUID
    run_id: uuid.UUID | None = None
    user_id: uuid.UUID
    project_id: uuid.UUID | None = None
    artifact_type: str
    name: str
    uri: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    checksum: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime
