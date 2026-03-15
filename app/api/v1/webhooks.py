"""Webhook management endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.common import OrmBase
from app.services.webhook_service import WebhookService

router = APIRouter()


class WebhookCreate(BaseModel):
    user_id: uuid.UUID
    url: str
    events: str = Field(
        default="*",
        description="Comma-separated event types: memory.created, memory.updated, memory.archived, *",
    )
    secret: str | None = None
    max_retries: int = Field(default=3, ge=1, le=10)


class WebhookResponse(OrmBase):
    id: uuid.UUID
    user_id: uuid.UUID
    url: str
    events: str
    is_active: bool
    max_retries: int
    created_at: datetime
    updated_at: datetime


@router.post("", response_model=WebhookResponse, status_code=201)
async def register_webhook(
    data: WebhookCreate,
    session: AsyncSession = Depends(get_session),
) -> WebhookResponse:
    """Register a new webhook endpoint."""
    svc = WebhookService(session)
    webhook = await svc.register(
        user_id=data.user_id,
        url=data.url,
        events=data.events,
        secret=data.secret,
        max_retries=data.max_retries,
    )
    return WebhookResponse.model_validate(webhook)


@router.get("", response_model=list[WebhookResponse])
async def list_webhooks(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[WebhookResponse]:
    """List all active webhooks for a user."""
    svc = WebhookService(session)
    webhooks = await svc.list_webhooks(user_id)
    return [WebhookResponse.model_validate(w) for w in webhooks]


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Deactivate a webhook."""
    svc = WebhookService(session)
    await svc.delete_webhook(webhook_id)
