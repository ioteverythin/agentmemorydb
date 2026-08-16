"""Lifecycle event emission — fire webhooks and WebSocket events on changes.

Memory writes and pipeline transitions emit typed lifecycle events so that
registered webhooks receive HMAC-signed deliveries and connected WebSocket
clients get live updates. Emission is **best-effort**: a failing webhook
endpoint or a slow WebSocket client can never break the primary write — every
sink is guarded and only logs on failure. Emission is also config-gated
(``emit_lifecycle_events``, ``enable_webhooks``, ``enable_websocket``).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.memory import Memory

logger = logging.getLogger("engramdb.lifecycle")


def memory_event_payload(memory: Memory) -> dict[str, Any]:
    """Build the event payload broadcast for a memory lifecycle change."""
    return {
        "memory_id": str(memory.id),
        "user_id": str(memory.user_id),
        "project_id": str(memory.project_id) if memory.project_id else None,
        "memory_key": memory.memory_key,
        "memory_type": memory.memory_type,
        "layer": memory.layer,
        "scope": memory.scope,
        "status": memory.status,
        "version": memory.version,
    }


async def emit_lifecycle_event(
    session: AsyncSession,
    *,
    event_type: str,
    user_id: uuid.UUID,
    data: dict[str, Any],
    project_id: uuid.UUID | None = None,
    memory_id: uuid.UUID | None = None,
) -> None:
    """Emit ``event_type`` to WebSocket subscribers and matching webhooks.

    Never raises: both sinks are independently guarded so a lifecycle event can
    be attached to any write path without making that write fragile.
    """
    if not settings.emit_lifecycle_events:
        return

    # ── WebSocket broadcast (best-effort) ───────────────────────
    if settings.enable_websocket:
        try:
            from app.ws import emit_memory_event

            await emit_memory_event(
                event_type,
                data,
                user_id=str(user_id),
                project_id=str(project_id) if project_id else None,
                memory_id=str(memory_id) if memory_id else None,
            )
        except Exception:
            logger.warning("WebSocket emit failed for %s", event_type, exc_info=True)

    # ── Webhook dispatch (best-effort) ──────────────────────────
    if settings.enable_webhooks:
        try:
            from app.services.webhook_service import WebhookService

            await WebhookService(session).dispatch(user_id, event_type, data)
        except Exception:
            logger.warning("Webhook dispatch failed for %s", event_type, exc_info=True)
