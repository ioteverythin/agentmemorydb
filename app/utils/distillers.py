"""Pluggable distillation strategies for the memory pyramid.

Distillation rolls lower-layer memories up into higher, more stable layers:
``atom → scenario`` (group related facts into a working-context block) and
``scenario → persona`` (synthesise a durable profile). The default
``HeuristicDistiller`` is deterministic and dependency-free so it is fully
testable and vendor-neutral; a deployment can drop in an LLM-backed distiller
via :func:`set_distiller` without touching the service layer (mirroring the
embedding-provider pattern).

The contract is intentionally content-only — a distiller sees the memories'
text and metadata and returns text — so it never needs DB access and can't
introduce cross-tenant leakage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class DistillItem:
    """A minimal, DB-free view of a memory for distillation."""

    memory_key: str
    content: str
    importance_score: float
    layer: str
    payload: dict | None = None


@runtime_checkable
class MemoryDistiller(Protocol):
    """Strategy for rolling memories up the pyramid."""

    def topic_of(self, item: DistillItem) -> str:
        """Return the grouping topic for an atom memory."""

    def scenario_digest(self, topic: str, atoms: list[DistillItem], *, char_budget: int) -> str:
        """Summarise a group of atoms into a scenario block."""

    def persona_synthesis(self, blocks: list[DistillItem], *, char_budget: int) -> str:
        """Synthesise a durable persona from scenario/atom blocks."""


class HeuristicDistiller:
    """Deterministic, LLM-free distiller.

    - Topic = explicit ``payload["topic"]`` if present, else the ``memory_key``
      namespace (text before the first ``:`` or ``/``), else ``"general"``.
    - Scenario/persona digests are importance-ordered, de-duplicated bullet
      lists, capped to a character budget.
    """

    def topic_of(self, item: DistillItem) -> str:
        if item.payload and isinstance(item.payload.get("topic"), str):
            return item.payload["topic"].strip() or "general"
        key = item.memory_key
        for sep in (":", "/"):
            if sep in key:
                return key.split(sep, 1)[0].strip() or "general"
        return "general"

    def scenario_digest(self, topic: str, atoms: list[DistillItem], *, char_budget: int) -> str:
        header = f"Scenario · {topic}"
        return self._bullets(header, atoms, char_budget)

    def persona_synthesis(self, blocks: list[DistillItem], *, char_budget: int) -> str:
        return self._bullets("User profile", blocks, char_budget)

    @staticmethod
    def _bullets(header: str, items: list[DistillItem], char_budget: int) -> str:
        lines = [header]
        seen: set[str] = set()
        # Most important first; deterministic tie-break by key.
        for it in sorted(items, key=lambda x: (-x.importance_score, x.memory_key)):
            body = " ".join(it.content.split())
            if not body or body.lower() in seen:
                continue
            seen.add(body.lower())
            candidate = f"- {body}"
            projected = "\n".join([*lines, candidate])
            if len(projected) > char_budget:
                break
            lines.append(candidate)
        return "\n".join(lines)


# ── Module-level pluggable singleton ────────────────────────────────

_distiller: MemoryDistiller = HeuristicDistiller()


def get_distiller() -> MemoryDistiller:
    return _distiller


def set_distiller(distiller: MemoryDistiller) -> None:
    """Override the active distiller (e.g. an LLM-backed strategy)."""
    global _distiller
    _distiller = distiller
