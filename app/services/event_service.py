"""Event service — append-only event log management."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.event import Event
from app.repositories.event_repository import EventRepository
from app.schemas.event import EventCreate
from app.utils.masking import get_default_engine


def _mask_if_enabled(text: str | None) -> str | None:
    if not text:
        return text
    engine = get_default_engine()
    if not engine.active_patterns:
        return text
    result = engine.mask_text(text)
    return result.masked_text if result.was_modified else text


class EventService:
    """Handles creation and retrieval of immutable events."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = EventRepository(session)

    async def create_event(self, data: EventCreate) -> Event:
        """Append a new event to the log.

        Events are immutable once created.  They represent raw signals
        from user input, tool calls, planner steps, etc.
        """
        masked_content = _mask_if_enabled(data.content)
        event = Event(
            run_id=data.run_id,
            user_id=data.user_id,
            event_type=data.event_type,
            content=masked_content,
            payload=data.payload,
            source=data.source,
            sequence_number=data.sequence_number,
        )
        return await self._repo.create(event)

    async def get_event(self, event_id: uuid.UUID) -> Event:
        event = await self._repo.get_by_id(event_id)
        if event is None:
            raise NotFoundError("Event", event_id)
        return event

    async def list_events_by_run(self, run_id: uuid.UUID) -> Sequence[Event]:
        """Return all events for a run, ordered by creation time."""
        return await self._repo.list_by_run(run_id)
