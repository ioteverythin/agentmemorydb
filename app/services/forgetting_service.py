"""Forgetting — principled, auditable memory decay and erasure.

Three mechanisms, all logged:

1. **Retention archival** — a score blending recency, importance, and actual
   use replaces the blunt ``importance < 0.3`` rule. A rarely-flagged-important
   but frequently-recalled fact survives; a stale, unused, low-value one decays.
2. **Importance decay** — Ebbinghaus-style exponential decay since last access,
   floored so nothing vanishes outright. Paired with reconsolidation-on-retrieval
   (see :mod:`app.services.retrieval_service`), frequently-used memories resist
   decay, matching the biological reconsolidation literature.
3. **Auditable erasure** — hard deletion for GDPR "right to be forgotten",
   leaving a tombstone in ``forgetting_log`` with a SHA-256 of the erased
   content: proof of *what* was deleted without retaining it.

Distilled layers (persona, scenario) and ``pinned`` memories are exempt from
1 and 2 — they are deliberate artefacts, not raw churn.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import NotFoundError
from app.core.metrics import record_forgetting
from app.models.forgetting_log import ForgettingLog
from app.models.memory import Memory
from app.models.memory_access_log import MemoryAccessLog
from app.models.memory_version import MemoryVersion
from app.utils.scoring import compute_recency_score, compute_retention_score


def _aware(ts: datetime) -> datetime:
    """Coerce a possibly-naive timestamp (SQLite round-trips naive) to UTC."""
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts


def _max_ts(a: datetime, b: datetime | None) -> datetime:
    """The later of two timestamps, tolerating a missing second one."""
    a_ = _aware(a)
    if b is None:
        return a_
    b_ = _aware(b)
    return a_ if a_ >= b_ else b_


class ForgettingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _exempt_layers(self) -> set[str]:
        return {s.strip() for s in settings.forgetting_exempt_layers.split(",") if s.strip()}

    async def archive_low_retention(self, *, dry_run: bool = False) -> dict:
        """Archive active memories whose retention score falls below threshold.

        A single grouped query pulls each eligible memory with its lifetime
        access count, retention is computed in Python, and the losers are
        archived in one UPDATE — no per-row round-trips.
        """
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=settings.forgetting_min_age_days)
        exempt = self._exempt_layers()

        # Eligible = active, older than min age, not distilled, not pinned.
        conds = [
            Memory.status == "active",
            Memory.updated_at < cutoff,
            Memory.pinned.is_(False),
        ]
        if exempt:
            conds.append(Memory.layer.notin_(exempt))

        stmt = (
            select(
                Memory.id,
                Memory.user_id,
                Memory.updated_at,
                Memory.importance_score,
                func.count(MemoryAccessLog.id).label("access_count"),
                func.max(MemoryAccessLog.created_at).label("last_access"),
            )
            .outerjoin(MemoryAccessLog, MemoryAccessLog.memory_id == Memory.id)
            .where(*conds)
            .group_by(Memory.id, Memory.user_id, Memory.updated_at, Memory.importance_score)
        )
        rows = (await self._session.execute(stmt)).all()

        threshold = settings.forgetting_retention_threshold
        to_archive: list = []
        owners: dict = {}
        for mem_id, owner_id, updated_at, importance, access_count, last_access in rows:
            # Recency tracks last *activity* — a write or a recall — so a
            # frequently-recalled memory reads as recently active and is kept.
            last_active = _max_ts(updated_at, last_access)
            retention = compute_retention_score(
                recency_score=compute_recency_score(last_active, now),
                importance_score=importance,
                access_count=int(access_count or 0),
                weight_recency=settings.forget_weight_recency,
                weight_importance=settings.forget_weight_importance,
                weight_access=settings.forget_weight_access,
                access_saturation=settings.forgetting_access_saturation,
            )
            if retention < threshold:
                to_archive.append(mem_id)
                owners[mem_id] = owner_id

        if to_archive and not dry_run:
            for mem_id in to_archive:
                self._log(
                    memory_id=mem_id,
                    user_id=owners[mem_id],
                    action="decayed_archive",
                    reason=f"retention below threshold {threshold}",
                    triggered_by="scheduler:archive_stale",
                )
            await self._session.execute(
                update(Memory)
                .where(Memory.id.in_(to_archive))
                .values(status="archived", updated_at=now)
            )
            record_forgetting("decayed_archive", len(to_archive))

        return {
            "candidates": len(rows),
            "archived": len(to_archive),
            "threshold": threshold,
            "dry_run": dry_run,
        }

    # ── Audit trail ─────────────────────────────────────────────
    def _log(
        self,
        *,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
        action: str,
        reason: str | None = None,
        triggered_by: str | None = None,
        content_hash: str | None = None,
    ) -> ForgettingLog:
        """Record a forgetting decision. Every removal path goes through here."""
        entry = ForgettingLog(
            memory_id=memory_id,
            user_id=user_id,
            action=action,
            reason=reason,
            triggered_by=triggered_by,
            content_hash=content_hash,
        )
        self._session.add(entry)
        return entry

    async def list_log(
        self, *, user_id: uuid.UUID | None = None, limit: int = 100, offset: int = 0
    ) -> Sequence[ForgettingLog]:
        stmt = select(ForgettingLog).order_by(ForgettingLog.occurred_at.desc())
        if user_id is not None:
            stmt = stmt.where(ForgettingLog.user_id == user_id)
        return (await self._session.execute(stmt.limit(limit).offset(offset))).scalars().all()

    # ── Importance decay (Ebbinghaus-style) ─────────────────────
    async def decay_importance(self, *, dry_run: bool = False) -> dict:
        """Decay importance exponentially since each memory's last access.

        ``importance *= 2 ** (-Δt / half_life)`` — a true half-life, so after
        ``DECAY_HALF_LIFE_HOURS`` of no use the importance has halved (the naive
        ``exp(-Δt / half_life)`` would leave 37%, not 50%). Floored at
        ``DECAY_FLOOR`` so a memory never disappears purely through decay, and
        pinned memories are skipped entirely. Paired with
        reconsolidation-on-retrieval, this makes *use* — not age alone — the
        thing that keeps a memory important.
        """
        now = datetime.now(UTC)
        half_life = max(settings.decay_half_life_hours, 1e-6)
        floor = settings.decay_floor

        stmt = (
            select(
                Memory.id,
                Memory.importance_score,
                Memory.updated_at,
                func.max(MemoryAccessLog.created_at).label("last_access"),
            )
            .outerjoin(MemoryAccessLog, MemoryAccessLog.memory_id == Memory.id)
            .where(Memory.status == "active", Memory.pinned.is_(False))
            .group_by(Memory.id, Memory.importance_score, Memory.updated_at)
        )
        rows = (await self._session.execute(stmt)).all()

        decayed = 0
        for mem_id, importance, updated_at, last_access in rows:
            if importance <= floor:
                continue
            last_active = _max_ts(updated_at, last_access)
            age_hours = max((now - last_active).total_seconds() / 3600.0, 0.0)
            retained = math.exp(-math.log(2.0) * age_hours / half_life)
            new_importance = max(importance * retained, floor)
            if new_importance < importance - 1e-9:
                decayed += 1
                if not dry_run:
                    await self._session.execute(
                        update(Memory)
                        .where(Memory.id == mem_id)
                        .values(importance_score=round(new_importance, 6))
                    )

        if decayed and not dry_run:
            record_forgetting("decayed", decayed)

        return {
            "considered": len(rows),
            "decayed": decayed,
            "half_life_hours": half_life,
            "floor": floor,
            "dry_run": dry_run,
        }

    # ── Auditable erasure (GDPR right-to-be-forgotten) ──────────
    async def erase_memory(
        self,
        memory_id: uuid.UUID,
        *,
        action: str = "user_erasure",
        reason: str | None = None,
        triggered_by: str | None = None,
    ) -> dict:
        """Hard-delete a memory and all its versions, leaving a tombstone.

        The content is gone; the ``forgetting_log`` row keeps its SHA-256 so an
        auditor can prove what was erased without the data surviving.
        """
        memory = await self._session.get(Memory, memory_id)
        if memory is None:
            raise NotFoundError("Memory", memory_id)

        self._log(
            memory_id=memory.id,
            user_id=memory.user_id,
            action=action,
            reason=reason,
            triggered_by=triggered_by,
            content_hash=memory.content_hash,
        )
        # Versions cascade via FK, but delete explicitly so the intent is clear
        # (and so the behaviour does not depend on cascade configuration).
        await self._session.execute(
            delete(MemoryVersion).where(MemoryVersion.memory_id == memory.id)
        )
        await self._session.delete(memory)
        await self._session.flush()
        record_forgetting(action)
        return {"erased": 1, "memory_id": str(memory_id), "action": action}

    async def erase_user_memories(
        self,
        user_id: uuid.UUID,
        *,
        action: str = "user_erasure",
        reason: str | None = None,
        triggered_by: str | None = None,
    ) -> dict:
        """Erase every memory for a user (full right-to-be-forgotten)."""
        memories = (
            (await self._session.execute(select(Memory).where(Memory.user_id == user_id)))
            .scalars()
            .all()
        )
        for memory in memories:
            self._log(
                memory_id=memory.id,
                user_id=user_id,
                action=action,
                reason=reason,
                triggered_by=triggered_by,
                content_hash=memory.content_hash,
            )
            await self._session.execute(
                delete(MemoryVersion).where(MemoryVersion.memory_id == memory.id)
            )
            await self._session.delete(memory)
        await self._session.flush()
        record_forgetting(action, len(memories))
        return {"erased": len(memories), "user_id": str(user_id), "action": action}

    # ── Expiry (TTL retraction, audited) ────────────────────────
    async def retract_expired(self) -> dict:
        """Retract memories past their ``expires_at``, recording each retraction.

        The outcome is unchanged from the pre-008 job — the memories are still
        marked ``retracted`` — but every retraction now leaves an audit row, so
        "why did this memory stop being retrievable?" is always answerable.
        """
        now = datetime.now(UTC)
        rows = (
            await self._session.execute(
                select(Memory.id, Memory.user_id).where(
                    Memory.status == "active",
                    Memory.expires_at.is_not(None),
                    Memory.expires_at < now,
                )
            )
        ).all()

        if rows:
            for mem_id, owner_id in rows:
                self._log(
                    memory_id=mem_id,
                    user_id=owner_id,
                    action="expired",
                    reason="past expires_at",
                    triggered_by="scheduler:cleanup_expired",
                )
            await self._session.execute(
                update(Memory)
                .where(Memory.id.in_([r[0] for r in rows]))
                .values(status="retracted", updated_at=now)
            )
            record_forgetting("expired", len(rows))

        return {"retracted_count": len(rows)}
