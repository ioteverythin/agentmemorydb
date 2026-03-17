"""WebSocket route handler for real-time memory events."""

from __future__ import annotations

import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.ws import get_connection_manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    channels: str | None = Query(default=None),
):
    """WebSocket endpoint for real-time memory event streaming.

    Connect with optional channel subscriptions:
        ws://host/ws?channels=user:abc-123,project:def-456

    Channel patterns:
        - user:{user_id}       → events for a specific user
        - project:{project_id} → events for a project
        - memory:{memory_id}   → changes to a specific memory
        - global               → all events

    Once connected, you can send JSON commands:
        {"action": "subscribe", "channel": "user:abc-123"}
        {"action": "unsubscribe", "channel": "user:abc-123"}
        {"action": "ping"}
    """
    manager = get_connection_manager()

    # Parse initial channel subscriptions
    channel_list = channels.split(",") if channels else ["global"]
    channel_list = [c.strip() for c in channel_list if c.strip()]

    await manager.connect(websocket, channel_list)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                action = msg.get("action", "")

                if action == "subscribe":
                    channel = msg.get("channel", "")
                    if channel:
                        await manager.subscribe(websocket, channel)
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "event": "subscribed",
                                    "channel": channel,
                                }
                            )
                        )

                elif action == "unsubscribe":
                    channel = msg.get("channel", "")
                    if channel:
                        await manager.unsubscribe(websocket, channel)
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "event": "unsubscribed",
                                    "channel": channel,
                                }
                            )
                        )

                elif action == "ping":
                    await websocket.send_text(
                        json.dumps(
                            {
                                "event": "pong",
                                "active_connections": manager.active_connections,
                            }
                        )
                    )

                elif action == "status":
                    await websocket.send_text(
                        json.dumps(
                            {
                                "event": "status",
                                "active_connections": manager.active_connections,
                                "subscriptions": manager.subscription_counts,
                            }
                        )
                    )

            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps(
                        {
                            "event": "error",
                            "message": "Invalid JSON",
                        }
                    )
                )

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
