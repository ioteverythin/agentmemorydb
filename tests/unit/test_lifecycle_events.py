"""Tests that memory writes actually fire lifecycle events — WebSocket
broadcasts and webhook deliveries — which were previously dead code."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from app.core.config import settings
from app.models.user import User
from app.models.webhook import Webhook, WebhookDelivery
from app.schemas.memory import MemoryStatusUpdate, MemoryUpsert
from app.services.memory_service import MemoryService
from app.ws import get_connection_manager


class FakeWebSocket:
    """Minimal stand-in for a connected WebSocket client."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def accept(self) -> None:
        pass

    async def send_text(self, text: str) -> None:
        self.sent.append(text)


async def _user(session) -> uuid.UUID:
    uid = uuid.uuid4()
    session.add(User(id=uid, name="evt-user"))
    await session.flush()
    return uid


@pytest.mark.unit
class TestWebSocketEmission:
    @pytest.mark.asyncio
    async def test_create_broadcasts_memory_created(self, unit_session):
        user_id = await _user(unit_session)
        manager = get_connection_manager()
        ws = FakeWebSocket()
        await manager.connect(ws, channels=[f"user:{user_id}"])
        try:
            svc = MemoryService(unit_session)
            await svc.upsert(
                MemoryUpsert(
                    user_id=user_id,
                    memory_key="k1",
                    memory_type="semantic",
                    content="hello",
                )
            )
            assert ws.sent, "expected a WebSocket broadcast"
            payload = json.loads(ws.sent[-1])
            assert payload["event"] == "memory.created"
            assert payload["data"]["memory_key"] == "k1"
        finally:
            await manager.disconnect(ws)

    @pytest.mark.asyncio
    async def test_status_change_broadcasts_archived(self, unit_session):
        user_id = await _user(unit_session)
        svc = MemoryService(unit_session)
        mem, _ = await svc.upsert(
            MemoryUpsert(user_id=user_id, memory_key="k2", memory_type="semantic", content="x")
        )
        manager = get_connection_manager()
        ws = FakeWebSocket()
        await manager.connect(ws, channels=[f"memory:{mem.id}"])
        try:
            await svc.update_status(mem.id, MemoryStatusUpdate(status="archived"))
            events = [json.loads(m)["event"] for m in ws.sent]
            assert "memory.archived" in events
        finally:
            await manager.disconnect(ws)

    @pytest.mark.asyncio
    async def test_emit_false_suppresses(self, unit_session):
        user_id = await _user(unit_session)
        manager = get_connection_manager()
        ws = FakeWebSocket()
        await manager.connect(ws, channels=[f"user:{user_id}"])
        try:
            svc = MemoryService(unit_session)
            await svc.upsert(
                MemoryUpsert(user_id=user_id, memory_key="k3", memory_type="semantic", content="y"),
                emit=False,
            )
            assert ws.sent == []
        finally:
            await manager.disconnect(ws)

    @pytest.mark.asyncio
    async def test_global_flag_disables_emission(self, unit_session):
        user_id = await _user(unit_session)
        manager = get_connection_manager()
        ws = FakeWebSocket()
        await manager.connect(ws, channels=["global"])
        prev = settings.emit_lifecycle_events
        settings.emit_lifecycle_events = False
        try:
            svc = MemoryService(unit_session)
            await svc.upsert(
                MemoryUpsert(user_id=user_id, memory_key="k4", memory_type="semantic", content="z")
            )
            assert ws.sent == []
        finally:
            settings.emit_lifecycle_events = prev
            await manager.disconnect(ws)


@pytest.mark.unit
class TestWebhookEmission:
    @pytest.mark.asyncio
    async def test_create_delivers_webhook(self, unit_session, monkeypatch):
        user_id = await _user(unit_session)

        # Register a wildcard webhook for this user.
        unit_session.add(
            Webhook(
                user_id=user_id,
                url="https://example.test/hook",
                events="*",
                secret="s3cr3t",
                max_retries=1,
            )
        )
        await unit_session.flush()

        # Stub the outbound HTTP call so no real network is hit.
        class FakeResp:
            status_code = 200
            text = "ok"

        async def fake_post(self, url, content=None, headers=None):
            # The signed body must be present and well-formed.
            assert headers.get("X-Webhook-Signature", "").startswith("sha256=")
            assert json.loads(content)["event_type"] == "memory.created"
            return FakeResp()

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

        svc = MemoryService(unit_session)
        await svc.upsert(
            MemoryUpsert(user_id=user_id, memory_key="wk", memory_type="semantic", content="c")
        )

        from sqlalchemy import select

        rows = (await unit_session.execute(select(WebhookDelivery))).scalars().all()
        assert len(rows) == 1
        assert rows[0].success is True
        assert rows[0].event_type == "memory.created"

    @pytest.mark.asyncio
    async def test_non_matching_event_not_delivered(self, unit_session, monkeypatch):
        user_id = await _user(unit_session)
        unit_session.add(
            Webhook(
                user_id=user_id,
                url="https://example.test/hook",
                events="memory.archived",  # not memory.created
                max_retries=1,
            )
        )
        await unit_session.flush()

        called = False

        async def fake_post(self, url, content=None, headers=None):
            nonlocal called
            called = True

            class R:
                status_code = 200
                text = ""

            return R()

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

        svc = MemoryService(unit_session)
        await svc.upsert(
            MemoryUpsert(user_id=user_id, memory_key="wk2", memory_type="semantic", content="c")
        )
        assert called is False
