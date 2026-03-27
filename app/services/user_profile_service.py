"""User profile synthesis service.

Inspired by EverMemOS's Semantic Consolidation step which distils user
MemCells into stable MemScene profiles.

Instead of requiring an LLM (which would add an external dependency),
this service builds a structured profile *from the memories themselves*:
it gathers the user's most important semantic and episodic memories and
writes a canonical ``semantic`` memory with key ``__profile__`` that
summarises them as a JSON payload.  Downstream retrieval and LLM prompts
can inject this profile for instant user context.

The job is idempotent — it always upserts the same key, so running it
multiple times only updates, never creates duplicates.

If ``OPENAI_API_KEY`` is set the service calls OpenAI to produce a
natural-language narrative summary in addition to the structured payload.
Without it, the payload alone is written (still useful for metadata
filtering and direct inspection).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory

logger = logging.getLogger("agentmemodb.profile")

# The canonical key for auto-synthesised profiles
PROFILE_KEY = "__profile__"
PROFILE_SOURCE_TYPE = "system_inference"
PROFILE_SCOPE = "user"
PROFILE_MEMORY_TYPE = "semantic"

# How many top memories to use as input
MAX_INPUT_MEMORIES = 20


class UserProfileService:
    """Synthesise a structured user profile from existing memories.

    Usage::

        async with async_session_factory() as session:
            svc = UserProfileService(session)
            result = await svc.synthesize(user_id=uid)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def synthesize(self, user_id: uuid.UUID) -> dict:
        """Build and upsert a ``__profile__`` memory for the given user.

        Returns a summary dict with counts and the generated profile key.
        """
        # ── Gather top memories ─────────────────────────────────
        stmt = (
            select(Memory)
            .where(
                and_(
                    Memory.user_id == user_id,
                    Memory.status == "active",
                    Memory.memory_key != PROFILE_KEY,
                    Memory.memory_type.in_(["semantic", "episodic", "procedural"]),
                )
            )
            .order_by(Memory.importance_score.desc(), Memory.updated_at.desc())
            .limit(MAX_INPUT_MEMORIES)
        )
        result = await self._session.execute(stmt)
        memories: list[Memory] = list(result.scalars().all())

        if not memories:
            return {"user_id": str(user_id), "status": "skipped", "reason": "no_memories"}

        # ── Build structured payload ────────────────────────────
        by_type: dict[str, list[str]] = {}
        for m in memories:
            bucket = by_type.setdefault(m.memory_type, [])
            bucket.append(m.content)

        payload = {
            "__type": "user_profile",
            "__generated_at": datetime.now(UTC).isoformat(),
            "__memory_count": len(memories),
            "memory_types": {k: len(v) for k, v in by_type.items()},
            "highlights": by_type,  # top N contents per type
        }

        # ── Optionally produce narrative with OpenAI ────────────
        narrative = await self._narrative(memories)

        content = narrative or self._plain_summary(by_type)

        # ── Upsert the profile memory ───────────────────────────
        existing_stmt = select(Memory).where(
            and_(
                Memory.user_id == user_id,
                Memory.memory_key == PROFILE_KEY,
                Memory.scope == PROFILE_SCOPE,
            )
        )
        existing = (await self._session.execute(existing_stmt)).scalar_one_or_none()

        now = datetime.now(UTC)
        if existing is None:
            profile = Memory(
                user_id=user_id,
                memory_key=PROFILE_KEY,
                memory_type=PROFILE_MEMORY_TYPE,
                scope=PROFILE_SCOPE,
                content=content,
                content_hash=_hash(content),
                payload=payload,
                source_type=PROFILE_SOURCE_TYPE,
                authority_level=3,  # system-generated, high authority
                confidence=0.9,
                importance_score=0.95,  # profile should always surface first
                recency_score=1.0,
                status="active",
                version=1,
                created_at=now,
                updated_at=now,
            )
            self._session.add(profile)
            action = "created"
        else:
            existing.content = content
            existing.content_hash = _hash(content)
            existing.payload = payload
            existing.importance_score = 0.95
            existing.updated_at = now
            self._session.add(existing)
            action = "updated"

        await self._session.flush()

        return {
            "user_id": str(user_id),
            "status": "ok",
            "action": action,
            "input_memories": len(memories),
            "memory_key": PROFILE_KEY,
        }

    def _plain_summary(self, by_type: dict[str, list[str]]) -> str:
        """Build a plain-text summary without an LLM."""
        lines = ["User profile (auto-generated):"]
        for mtype, contents in by_type.items():
            lines.append(f"\n[{mtype.upper()}]")
            for c in contents[:5]:
                lines.append(f"  - {c[:120]}")
        return "\n".join(lines)

    async def _narrative(self, memories: list[Memory]) -> str | None:
        """Call OpenAI to produce a paragraph narrative. Returns None if unavailable."""
        try:
            from app.core.config import settings

            if not settings.openai_api_key:
                return None

            import httpx

            snippets = "\n".join(f"- [{m.memory_type}] {m.content[:200]}" for m in memories[:15])
            prompt = (
                "You are a memory system. Based on the following agent memories, "
                "write a concise 3–5 sentence profile of this user. "
                "Focus on persistent traits, goals, preferences, and working context.\n\n"
                f"Memories:\n{snippets}\n\nProfile:"
            )

            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 200,
                        "temperature": 0.3,
                    },
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.debug("OpenAI profile narrative unavailable: %s", exc)
            return None


def _hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()
