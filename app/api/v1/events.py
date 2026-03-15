"""Event endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.event import EventCreate, EventResponse
from app.schemas.observation import ObservationResponse
from app.services.event_service import EventService
from app.services.observation_service import ObservationService

router = APIRouter()


@router.post("", response_model=EventResponse, status_code=201)
async def create_event(
    data: EventCreate,
    session: AsyncSession = Depends(get_session),
) -> EventResponse:
    svc = EventService(session)
    event = await svc.create_event(data)
    return EventResponse.model_validate(event)


@router.get("/{event_id}/observations", response_model=list[ObservationResponse])
async def list_event_observations(
    event_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[ObservationResponse]:
    svc = ObservationService(session)
    observations = await svc.list_by_event(event_id)
    return [ObservationResponse.model_validate(o) for o in observations]
