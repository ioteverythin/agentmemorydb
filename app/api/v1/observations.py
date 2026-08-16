"""Observation endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.memory import MemoryResponse
from app.schemas.observation import (
    ObservationCreate,
    ObservationExtractRequest,
    ObservationPromoteRequest,
    ObservationPromoteResponse,
    ObservationRejectRequest,
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


@router.get("/{observation_id}", response_model=ObservationResponse)
async def get_observation(
    observation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ObservationResponse:
    svc = ObservationService(session)
    obs = await svc.get_observation(observation_id)
    return ObservationResponse.model_validate(obs)


@router.post("/{observation_id}/promote", response_model=ObservationPromoteResponse)
async def promote_observation(
    observation_id: uuid.UUID,
    data: ObservationPromoteRequest,
    session: AsyncSession = Depends(get_session),
) -> ObservationPromoteResponse:
    """Promote a candidate observation into a canonical memory.

    Completes the Event → Observation → Memory pipeline: upserts the
    observation's content as a memory (carrying provenance), marks the
    observation ``accepted``, and links it to the memory.
    """
    svc = ObservationService(session)
    obs, memory, memory_created = await svc.promote(observation_id, data)
    return ObservationPromoteResponse(
        observation=ObservationResponse.model_validate(obs),
        memory=MemoryResponse.model_validate(memory),
        memory_created=memory_created,
    )


@router.post("/{observation_id}/reject", response_model=ObservationResponse)
async def reject_observation(
    observation_id: uuid.UUID,
    data: ObservationRejectRequest,
    session: AsyncSession = Depends(get_session),
) -> ObservationResponse:
    """Reject a candidate observation so it is never promoted."""
    svc = ObservationService(session)
    obs = await svc.reject(observation_id, data.reason)
    return ObservationResponse.model_validate(obs)
