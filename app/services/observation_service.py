"""Observation service — candidate memory extraction from events."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models.memory import Memory
from app.models.observation import Observation
from app.repositories.event_repository import EventRepository
from app.repositories.observation_repository import ObservationRepository
from app.schemas.memory import MemoryUpsert
from app.schemas.observation import ObservationCreate, ObservationPromoteRequest
from app.services.lifecycle import emit_lifecycle_event
from app.utils.masking import get_default_engine
from app.ws import MemoryEventTypes


def _mask_if_enabled(text: str | None) -> str | None:
    if not text:
        return text
    engine = get_default_engine()
    if not engine.active_patterns:
        return text
    result = engine.mask_text(text)
    return result.masked_text if result.was_modified else text


class ObservationService:
    """Manages the creation and lifecycle of candidate observations.

    Observations sit between raw events and canonical memories.
    They represent *potential* facts or knowledge extracted from events
    that can later be promoted into the memory store via upsert.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ObservationRepository(session)
        self._event_repo = EventRepository(session)

    async def create_observation(self, data: ObservationCreate) -> Observation:
        """Create a manually-specified observation."""
        masked_content = _mask_if_enabled(data.content)
        obs = Observation(
            event_id=data.event_id,
            run_id=data.run_id,
            user_id=data.user_id,
            content=masked_content,
            observation_type=data.observation_type,
            source_type=data.source_type,
            confidence=data.confidence,
            metadata_=data.metadata,
            status="pending",
        )
        obs = await self._repo.create(obs)
        await emit_lifecycle_event(
            self._session,
            event_type=MemoryEventTypes.OBSERVATION_CREATED,
            user_id=obs.user_id,
            data={"observation_id": str(obs.id), "event_id": str(obs.event_id)},
        )
        return obs

    async def extract_from_event(self, event_id: uuid.UUID) -> list[Observation]:
        """Rule-based extraction of observations from an event.

        This is a deterministic heuristic implementation.
        TODO: Add LLM-based extraction as a pluggable strategy.

        Current rules:
        - user_input / tool_result events with content → one observation
        - model_output events → one observation per non-empty content
        - Other event types are ignored for now
        """
        event = await self._event_repo.get_by_id(event_id)
        if event is None:
            raise NotFoundError("Event", event_id)

        observations: list[Observation] = []
        extractable_types = {"user_input", "tool_result", "model_output"}

        if event.event_type in extractable_types and event.content:
            source_type = "user_input" if event.event_type == "user_input" else "system_inference"
            confidence = 0.8 if event.event_type == "user_input" else 0.5

            obs = Observation(
                event_id=event.id,
                run_id=event.run_id,
                user_id=event.user_id,
                content=_mask_if_enabled(event.content) or event.content,
                observation_type=event.event_type,
                source_type=source_type,
                confidence=confidence,
                metadata_={"extraction_method": "rule_based", "event_type": event.event_type},
                status="pending",
            )
            obs = await self._repo.create(obs)
            observations.append(obs)

        # TODO: LLM-based extraction hook
        # if llm_extractor is not None:
        #     additional = await llm_extractor.extract(event)
        #     observations.extend(additional)

        return observations

    async def list_by_event(self, event_id: uuid.UUID) -> Sequence[Observation]:
        """Return all observations for a given event."""
        return await self._repo.list_by_event(event_id)

    async def get_observation(self, observation_id: uuid.UUID) -> Observation:
        obs = await self._repo.get_by_id(observation_id)
        if obs is None:
            raise NotFoundError("Observation", observation_id)
        return obs

    # ── Promotion: Observation → Memory ─────────────────────────
    async def promote(
        self, observation_id: uuid.UUID, req: ObservationPromoteRequest
    ) -> tuple[Observation, Memory, bool]:
        """Promote a candidate observation into a canonical memory.

        Completes the Event → Observation → Memory pipeline: the observation's
        content is upserted as a memory (carrying event/observation/run
        provenance), the observation is marked ``accepted`` and linked to the
        resulting memory. Returns ``(observation, memory, memory_created)``.
        """
        obs = await self.get_observation(observation_id)
        if obs.status == "rejected":
            raise ConflictError(f"Observation {observation_id} was rejected and cannot be promoted")

        # Local import avoids a service-layer import cycle.
        from app.services.memory_service import MemoryService

        upsert = MemoryUpsert(
            user_id=obs.user_id,
            project_id=req.project_id,
            memory_key=req.memory_key,
            memory_type=req.memory_type,
            layer=req.layer,
            scope=req.scope,
            content=obs.content,
            source_type="human_verified" if req.human_verified else obs.source_type,
            source_event_id=obs.event_id,
            source_observation_id=obs.id,
            source_run_id=obs.run_id,
            confidence=req.confidence if req.confidence is not None else obs.confidence,
            importance_score=req.importance_score,
            authority_level=req.authority_level,
            is_contradiction=req.is_contradiction,
        )
        memory, is_new = await MemoryService(self._session).upsert(upsert)

        obs.status = "accepted"
        obs.memory_id = memory.id

        await emit_lifecycle_event(
            self._session,
            event_type="observation.promoted",
            user_id=obs.user_id,
            data={
                "observation_id": str(obs.id),
                "memory_id": str(memory.id),
                "memory_created": is_new,
            },
            project_id=memory.project_id,
            memory_id=memory.id,
        )
        return obs, memory, is_new

    async def reject(self, observation_id: uuid.UUID, reason: str | None = None) -> Observation:
        """Reject a candidate observation so it is not promoted."""
        obs = await self.get_observation(observation_id)
        obs.status = "rejected"
        if reason:
            obs.metadata_ = {**(obs.metadata_ or {}), "rejection_reason": reason}
        return obs
