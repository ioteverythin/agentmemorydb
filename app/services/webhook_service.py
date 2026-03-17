"""Webhook service — registration, dispatch, and delivery auditing."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.metrics import record_webhook_delivery
from app.models.webhook import Webhook, WebhookDelivery

logger = logging.getLogger("agentmemorydb.webhooks")


class WebhookService:
    """Manages webhook registrations and dispatches events."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Registration ────────────────────────────────────────────

    async def register(
        self,
        user_id: uuid.UUID,
        url: str,
        events: str = "*",
        secret: str | None = None,
        max_retries: int = 3,
    ) -> Webhook:
        """Register a new webhook endpoint."""
        webhook = Webhook(
            user_id=user_id,
            url=url,
            events=events,
            secret=secret,
            max_retries=max_retries,
        )
        self._session.add(webhook)
        await self._session.flush()
        await self._session.refresh(webhook)
        return webhook

    async def list_webhooks(self, user_id: uuid.UUID) -> Sequence[Webhook]:
        stmt = select(Webhook).where(Webhook.user_id == user_id, Webhook.is_active.is_(True))
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def delete_webhook(self, webhook_id: uuid.UUID) -> bool:
        webhook = await self._session.get(Webhook, webhook_id)
        if webhook is None:
            return False
        webhook.is_active = False
        return True

    # ── Dispatch ────────────────────────────────────────────────

    async def dispatch(
        self,
        user_id: uuid.UUID,
        event_type: str,
        payload: dict[str, Any],
    ) -> list[WebhookDelivery]:
        """Dispatch an event to all matching active webhooks for a user."""
        webhooks = await self._get_matching_webhooks(user_id, event_type)
        deliveries: list[WebhookDelivery] = []

        async with httpx.AsyncClient(timeout=10.0) as client:
            for webhook in webhooks:
                delivery = await self._deliver(client, webhook, event_type, payload)
                deliveries.append(delivery)

        return deliveries

    async def _get_matching_webhooks(
        self, user_id: uuid.UUID, event_type: str
    ) -> Sequence[Webhook]:
        """Find all active webhooks that match the given event type."""
        stmt = select(Webhook).where(Webhook.user_id == user_id, Webhook.is_active.is_(True))
        result = await self._session.execute(stmt)
        all_hooks = result.scalars().all()

        matching = []
        for hook in all_hooks:
            subscribed = {e.strip() for e in hook.events.split(",")}
            if "*" in subscribed or event_type in subscribed:
                matching.append(hook)
        return matching

    async def _deliver(
        self,
        client: httpx.AsyncClient,
        webhook: Webhook,
        event_type: str,
        payload: dict[str, Any],
    ) -> WebhookDelivery:
        """Attempt to deliver a webhook with retry logic."""
        body = json.dumps(
            {
                "event_type": event_type,
                "timestamp": datetime.now(UTC).isoformat(),
                "data": payload,
            },
            default=str,
        )

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if webhook.secret:
            signature = hmac.new(webhook.secret.encode(), body.encode(), hashlib.sha256).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        last_delivery: WebhookDelivery | None = None
        for attempt in range(1, webhook.max_retries + 1):
            try:
                resp = await client.post(webhook.url, content=body, headers=headers)
                delivery = WebhookDelivery(
                    webhook_id=webhook.id,
                    event_type=event_type,
                    payload=json.loads(body),
                    status_code=resp.status_code,
                    response_body=resp.text[:2000] if resp.text else None,
                    success=200 <= resp.status_code < 300,
                    attempt=attempt,
                )
                self._session.add(delivery)
                record_webhook_delivery(event_type, delivery.success)

                if delivery.success:
                    await self._session.flush()
                    return delivery

                last_delivery = delivery
                logger.warning(
                    "Webhook delivery failed (attempt %d/%d): %s → %d",
                    attempt,
                    webhook.max_retries,
                    webhook.url,
                    resp.status_code,
                )
            except httpx.HTTPError as exc:
                delivery = WebhookDelivery(
                    webhook_id=webhook.id,
                    event_type=event_type,
                    payload=json.loads(body),
                    status_code=None,
                    response_body=str(exc)[:2000],
                    success=False,
                    attempt=attempt,
                )
                self._session.add(delivery)
                record_webhook_delivery(event_type, False)
                last_delivery = delivery
                logger.warning(
                    "Webhook delivery error (attempt %d/%d): %s → %s",
                    attempt,
                    webhook.max_retries,
                    webhook.url,
                    exc,
                )

        await self._session.flush()
        return last_delivery  # type: ignore[return-value]
