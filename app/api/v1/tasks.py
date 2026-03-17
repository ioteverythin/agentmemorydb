"""Task endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.task import TaskCreate, TaskResponse, TaskTransition
from app.services.task_service import TaskService

router = APIRouter()


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(
    data: TaskCreate,
    session: AsyncSession = Depends(get_session),
) -> TaskResponse:
    svc = TaskService(session)
    task = await svc.create_task(data)
    return TaskResponse.model_validate(task)


@router.patch("/{task_id}/transition", response_model=TaskResponse)
async def transition_task(
    task_id: uuid.UUID,
    data: TaskTransition,
    session: AsyncSession = Depends(get_session),
) -> TaskResponse:
    svc = TaskService(session)
    task = await svc.transition(task_id, data)
    return TaskResponse.model_validate(task)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TaskResponse:
    svc = TaskService(session)
    task = await svc.get_task(task_id)
    return TaskResponse.model_validate(task)


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    user_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    state: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[TaskResponse]:
    svc = TaskService(session)
    tasks = await svc.list_tasks(
        user_id=user_id,
        project_id=project_id,
        state=state,
        limit=limit,
        offset=offset,
    )
    return [TaskResponse.model_validate(t) for t in tasks]
