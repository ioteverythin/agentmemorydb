"""Distillation — the self-filling memory pyramid.

Rolls a user's lower-layer memories up into higher, more stable layers so the
pyramid maintains itself instead of relying on manual promotion:

    atom  ──group by topic──▶  scenario   (a working-context block per topic)
    scenario ──synthesise──▶   persona    (one durable profile: persona:core)

The distillation logic itself is delegated to a pluggable strategy
(:mod:`app.utils.distillers`); this service only handles selection, grouping,
and persisting the results as ordinary versioned memories (so scenario/persona
memories get audit history and lifecycle events for free). Runs are idempotent:
re-running updates the same ``scenario:<topic>`` / ``persona:core`` keys.
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.memory import Memory
from app.schemas.memory import MemoryUpsert
from app.services.memory_service import MemoryService
from app.utils.distillers import DistillItem, get_distiller


class DistillationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._memory_svc = MemoryService(session)

    async def _active_by_layer(
        self, user_id: uuid.UUID, layer: str, project_id: uuid.UUID | None
    ) -> list[Memory]:
        conds = [Memory.user_id == user_id, Memory.status == "active", Memory.layer == layer]
        if project_id is not None:
            conds.append(Memory.project_id == project_id)
        rows = await self._session.execute(select(Memory).where(and_(*conds)))
        return list(rows.scalars().all())

    @staticmethod
    def _item(m: Memory) -> DistillItem:
        return DistillItem(
            memory_key=m.memory_key,
            content=m.content,
            importance_score=m.importance_score,
            layer=m.layer,
            payload=m.payload,
        )

    async def distill(
        self,
        user_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Distil a user's atoms into scenarios, then a persona.

        Returns a report of what was (or, for ``dry_run``, would be) produced.
        """
        distiller = get_distiller()
        atoms = await self._active_by_layer(user_id, "atom", project_id)

        # ── atom → scenario ─────────────────────────────────────
        groups: dict[str, list[Memory]] = {}
        for m in atoms:
            topic = distiller.topic_of(self._item(m))
            groups.setdefault(topic, []).append(m)

        min_size = settings.distillation_min_group_size
        scenario_reports: list[dict] = []
        produced: list[DistillItem] = []

        for topic, members in sorted(groups.items()):
            if len(members) < min_size:
                continue
            digest = distiller.scenario_digest(
                topic,
                [self._item(m) for m in members],
                char_budget=settings.distillation_scenario_char_budget,
            )
            key = f"scenario:{topic}"
            produced.append(
                DistillItem(
                    memory_key=key,
                    content=digest,
                    importance_score=max(m.importance_score for m in members),
                    layer="scenario",
                )
            )
            report = {"topic": topic, "memory_key": key, "member_count": len(members)}
            if not dry_run:
                _mem, is_new = await self._memory_svc.upsert(
                    MemoryUpsert(
                        user_id=user_id,
                        project_id=project_id,
                        memory_key=key,
                        memory_type="semantic",
                        layer="scenario",
                        content=digest,
                        source_type="system_inference",
                        importance_score=min(1.0, max(m.importance_score for m in members)),
                        authority_level=max(m.authority_level for m in members),
                        payload={
                            "kind": "distilled",
                            "topic": topic,
                            "distilled_from": [m.memory_key for m in members],
                            "member_count": len(members),
                        },
                    )
                )
                report["created"] = is_new
            scenario_reports.append(report)

        # ── scenario → persona ──────────────────────────────────
        existing_scenarios = await self._active_by_layer(user_id, "scenario", project_id)
        produced_keys = {p.memory_key for p in produced}
        persona_sources = produced + [
            self._item(s) for s in existing_scenarios if s.memory_key not in produced_keys
        ]

        persona_updated = False
        if len(persona_sources) >= settings.distillation_min_scenarios_for_persona:
            content = distiller.persona_synthesis(
                persona_sources, char_budget=settings.distillation_persona_char_budget
            )
            # Only write a persona once there is real content beyond the header.
            if "\n" in content.strip():
                persona_updated = True
                if not dry_run:
                    await self._memory_svc.upsert(
                        MemoryUpsert(
                            user_id=user_id,
                            project_id=project_id,
                            memory_key="persona:core",
                            memory_type="semantic",
                            layer="persona",
                            content=content,
                            source_type="system_inference",
                            importance_score=0.9,
                            authority_level=max(
                                (s.authority_level for s in existing_scenarios), default=1
                            ),
                            payload={
                                "kind": "distilled",
                                "distilled_from": [p.memory_key for p in persona_sources],
                            },
                        )
                    )

        return {
            "atoms_considered": len(atoms),
            "scenarios": scenario_reports,
            "persona_updated": persona_updated,
            "dry_run": dry_run,
        }
