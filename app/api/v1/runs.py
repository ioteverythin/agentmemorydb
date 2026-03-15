"""AgentRun endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.session import get_session
from app.models.agent_run import AgentRun
from app.repositories.run_repository import RunRepository
from app.schemas.run import RunComplete, RunCreate, RunResponse
from app.schemas.event import EventResponse
from app.schemas.retrieval_log import RetrievalLogResponse
from app.services.event_service import EventService
from app.services.retrieval_log_service import RetrievalLogService

router = APIRouter()


@router.post("", response_model=RunResponse, status_code=201)
async def create_run(
    data: RunCreate,
    session: AsyncSession = Depends(get_session),
) -> RunResponse:
    repo = RunRepository(session)
    run = AgentRun(
        user_id=data.user_id,
        project_id=data.project_id,
        agent_name=data.agent_name,
        context=data.context,
        status="running",
    )
    run = await repo.create(run)
    return RunResponse.model_validate(run)


@router.patch("/{run_id}/complete", response_model=RunResponse)
async def complete_run(
    run_id: uuid.UUID,
    data: RunComplete,
    session: AsyncSession = Depends(get_session),
) -> RunResponse:
    repo = RunRepository(session)
    run = await repo.get_by_id(run_id)
    if run is None:
        raise NotFoundError("Run", run_id)
    run.status = "completed"
    run.summary = data.summary
    run.completed_at = datetime.now(timezone.utc)
    return RunResponse.model_validate(run)


@router.get("/{run_id}/events", response_model=list[EventResponse])
async def list_run_events(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[EventResponse]:
    svc = EventService(session)
    events = await svc.list_events_by_run(run_id)
    return [EventResponse.model_validate(e) for e in events]


@router.get("/{run_id}/retrieval-logs", response_model=list[RetrievalLogResponse])
async def list_run_retrieval_logs(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[RetrievalLogResponse]:
    svc = RetrievalLogService(session)
    logs = await svc.list_by_run(run_id)
    return [RetrievalLogResponse.model_validate(log) for log in logs]
