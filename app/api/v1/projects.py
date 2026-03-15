"""Project endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.project import Project
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectResponse

router = APIRouter()


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    data: ProjectCreate,
    session: AsyncSession = Depends(get_session),
) -> ProjectResponse:
    repo = ProjectRepository(session)
    project = Project(user_id=data.user_id, name=data.name, description=data.description)
    project = await repo.create(project)
    return ProjectResponse.model_validate(project)
