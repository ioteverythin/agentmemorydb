"""WebSocket real-time event streaming for AgentMemoryDB.

Inspired by InsForge's real-time pub/sub via PostgreSQL triggers + WebSockets.
Provides live streaming of memory lifecycle events to connected clients.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from collections import defaultdict

from fastapi import WebSocket, WebSocketDisconnect


class ConnectionManager:
    """Manages WebSocket connections and broadcasts memory events.

    Supports channel-based subscriptions so clients can listen to:
    - user:{user_id}     — all events for a specific user
    - project:{project_id} — all events for a project
    - memory:{memory_id}   — changes to a specific memory
    - global               — all events system-wide
    """

    def __init__(self) -> None:
        # channel_name -> set of websockets
        self._subscriptions: dict[str, set[WebSocket]] = defaultdict(set)
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, channels: list[str] | None = None) -> None:
        """Accept a WebSocket connection and subscribe to channels."""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
            for channel in (channels or ["global"]):
                self._subscriptions[channel].add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket from all subscriptions."""
        async with self._lock:
            self._connections.discard(websocket)
            for channel_subs in self._subscriptions.values():
                channel_subs.discard(websocket)

    async def subscribe(self, websocket: WebSocket, channel: str) -> None:
        """Subscribe a connected WebSocket to an additional channel."""
        async with self._lock:
            self._subscriptions[channel].add(websocket)

    async def unsubscribe(self, websocket: WebSocket, channel: str) -> None:
        """Unsubscribe a WebSocket from a channel."""
        async with self._lock:
            self._subscriptions[channel].discard(websocket)

    async def broadcast(self, event: MemoryEvent) -> None:
        """Broadcast a memory event to all relevant subscribers."""
        payload = json.dumps(event.to_dict(), default=str)
        channels_to_notify = set(event.channels + ["global"])

        dead_connections: set[WebSocket] = set()

        async with self._lock:
            targets: set[WebSocket] = set()
            for channel in channels_to_notify:
                targets.update(self._subscriptions.get(channel, set()))

        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead_connections.add(ws)

        # Clean up dead connections
        if dead_connections:
            for ws in dead_connections:
                await self.disconnect(ws)

    @property
    def active_connections(self) -> int:
        return len(self._connections)

    @property
    def subscription_counts(self) -> dict[str, int]:
        return {ch: len(subs) for ch, subs in self._subscriptions.items() if subs}


class MemoryEvent:
    """A real-time memory event for broadcasting."""

    def __init__(
        self,
        event_type: str,
        data: dict[str, Any],
        channels: list[str] | None = None,
    ) -> None:
        self.id = str(uuid.uuid4())
        self.event_type = event_type
        self.data = data
        self.channels = channels or []
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event": self.event_type,
            "data": self.data,
            "channels": self.channels,
            "timestamp": self.timestamp,
        }


# ── Predefined Event Types ─────────────────────────────────────

class MemoryEventTypes:
    """Standard memory event types for real-time streaming."""
    MEMORY_CREATED = "memory.created"
    MEMORY_UPDATED = "memory.updated"
    MEMORY_ARCHIVED = "memory.archived"
    MEMORY_RETRACTED = "memory.retracted"
    MEMORY_LINKED = "memory.linked"
    MEMORY_CONSOLIDATED = "memory.consolidated"
    EVENT_RECORDED = "event.recorded"
    OBSERVATION_CREATED = "observation.created"
    SEARCH_EXECUTED = "search.executed"
    GRAPH_TRAVERSED = "graph.traversed"


# ── Singleton Manager ────────────────────────────────────────────

_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """Get or create the global WebSocket connection manager."""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager


async def emit_memory_event(
    event_type: str,
    data: dict[str, Any],
    user_id: str | None = None,
    project_id: str | None = None,
    memory_id: str | None = None,
) -> None:
    """Convenience function to emit a memory event to relevant channels."""
    channels: list[str] = []
    if user_id:
        channels.append(f"user:{user_id}")
    if project_id:
        channels.append(f"project:{project_id}")
    if memory_id:
        channels.append(f"memory:{memory_id}")

    event = MemoryEvent(event_type=event_type, data=data, channels=channels)
    manager = get_connection_manager()
    await manager.broadcast(event)
