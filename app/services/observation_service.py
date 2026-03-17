"""Observation service — candidate memory extraction from events."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.observation import Observation
from app.repositories.event_repository import EventRepository
from app.repositories.observation_repository import ObservationRepository
from app.schemas.observation import ObservationCreate
from app.utils.masking import get_default_engine


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
        return await self._repo.create(obs)

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
