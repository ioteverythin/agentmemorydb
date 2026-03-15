"""Observation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.observation import (
    ObservationCreate,
    ObservationExtractRequest,
    ObservationResponse,
)
from app.services.observation_service import ObservationService

router = APIRouter()


@router.post("", response_model=ObservationResponse, status_code=201)
async def create_observation(
    data: ObservationCreate,
    session: AsyncSession = Depends(get_session),
) -> ObservationResponse:
    svc = ObservationService(session)
    obs = await svc.create_observation(data)
    return ObservationResponse.model_validate(obs)


@router.post("/extract-from-event", response_model=list[ObservationResponse], status_code=201)
async def extract_from_event(
    data: ObservationExtractRequest,
    session: AsyncSession = Depends(get_session),
) -> list[ObservationResponse]:
    """Rule-based observation extraction from a single event.

    TODO: Add LLM-based extraction as a pluggable strategy.
    """
    svc = ObservationService(session)
    observations = await svc.extract_from_event(data.event_id)
    return [ObservationResponse.model_validate(o) for o in observations]
