"""Artifact metadata endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.session import get_session
from app.models.artifact import ArtifactMetadata
from app.repositories.artifact_repository import ArtifactRepository
from app.schemas.artifact import ArtifactCreate, ArtifactResponse

router = APIRouter()


@router.post("", response_model=ArtifactResponse, status_code=201)
async def create_artifact(
    data: ArtifactCreate,
    session: AsyncSession = Depends(get_session),
) -> ArtifactResponse:
    repo = ArtifactRepository(session)
    artifact = ArtifactMetadata(
        run_id=data.run_id,
        user_id=data.user_id,
        project_id=data.project_id,
        artifact_type=data.artifact_type,
        name=data.name,
        uri=data.uri,
        mime_type=data.mime_type,
        size_bytes=data.size_bytes,
        checksum=data.checksum,
        metadata_=data.metadata,
    )
    artifact = await repo.create(artifact)
    return ArtifactResponse.model_validate(artifact)


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ArtifactResponse:
    repo = ArtifactRepository(session)
    artifact = await repo.get_by_id(artifact_id)
    if artifact is None:
        raise NotFoundError("Artifact", artifact_id)
    return ArtifactResponse.model_validate(artifact)
