"""Write provenance and poisoning resistance.

A memory store that ranks by authority and confidence is only as trustworthy as
its *writers*. If a fetched web page can write a memory claiming authority 4 and
confidence 1.0, it outranks what the user actually said — and the next retrieval
hands the agent the attacker's text as high-authority context. That is memory
poisoning, and it needs no exploit: just a write endpoint that believes its input.

Two mechanisms close that hole:

1. **Authority ceilings.** Every origin has a maximum ``authority_level`` it may
   claim. A write asking for more is *clamped*, not rejected — the fact is still
   worth storing, it just cannot outrank a more trusted writer. Rejecting would
   lose data; trusting would lose the ranking.
2. **Quarantine.** A low-confidence write from an untrusted origin lands in
   ``status="quarantined"``: stored and reviewable, but never retrieved and never
   assembled into a prompt until a human releases it.

Both are inert unless ``ENABLE_POISONING_RESISTANCE`` is on.
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.models.enums import MemoryOrigin

logger = logging.getLogger(__name__)

# ``authority_level`` runs 1 to 4 (see app/utils/scoring.py). The ceilings encode a
# trust ordering: what the user said outranks what the agent inferred, which
# outranks what a tool returned, which outranks whatever the open internet says.
AUTHORITY_CEILINGS: dict[MemoryOrigin, int] = {
    MemoryOrigin.OPERATOR: 4,
    MemoryOrigin.USER: 4,
    MemoryOrigin.SYSTEM: 3,
    MemoryOrigin.AGENT_INFERENCE: 3,
    MemoryOrigin.TOOL_OUTPUT: 2,
    MemoryOrigin.IMPORTED: 2,
    MemoryOrigin.EXTERNAL_INGEST: 1,
}

# Origins outside the trust boundary. Content arriving through these is treated
# as potentially adversarial and is eligible for quarantine.
UNTRUSTED_ORIGINS: frozenset[MemoryOrigin] = frozenset(
    {MemoryOrigin.EXTERNAL_INGEST, MemoryOrigin.TOOL_OUTPUT}
)

DEFAULT_ORIGIN = MemoryOrigin.AGENT_INFERENCE


def parse_origin(value: str | None) -> MemoryOrigin:
    """Coerce a wire value to a known origin, defaulting to agent inference.

    An unrecognised origin is *not* an error — but it is also not a licence to
    claim authority, so it falls back to the default rather than being trusted.
    """
    if value is None:
        return DEFAULT_ORIGIN
    try:
        return MemoryOrigin(value)
    except ValueError:
        logger.warning("Unknown memory origin %r; treating as %s", value, DEFAULT_ORIGIN)
        return DEFAULT_ORIGIN


def authority_ceiling(origin: str | MemoryOrigin) -> int:
    """The highest ``authority_level`` this origin is allowed to claim."""
    resolved = origin if isinstance(origin, MemoryOrigin) else parse_origin(origin)
    return AUTHORITY_CEILINGS.get(resolved, AUTHORITY_CEILINGS[DEFAULT_ORIGIN])


def clamp_authority(origin: str | MemoryOrigin, requested: int) -> tuple[int, bool]:
    """Clamp ``requested`` authority to the origin's ceiling.

    Returns ``(effective_authority, was_clamped)``. A no-op returning the
    request unchanged when the feature flag is off, so enabling it can only ever
    lower authority — never raise it.
    """
    if not settings.enable_poisoning_resistance:
        return requested, False
    ceiling = authority_ceiling(origin)
    if requested <= ceiling:
        return requested, False
    logger.warning(
        "Authority %d requested by origin %s exceeds its ceiling of %d; clamping.",
        requested,
        origin,
        ceiling,
    )
    return ceiling, True


def should_quarantine(origin: str | MemoryOrigin, confidence: float) -> bool:
    """Whether a write should land in quarantine instead of active recall.

    Only untrusted origins are eligible, and only below the confidence bar: a
    tool result the agent is sure about is ordinary data, while a low-confidence
    claim from a fetched page is exactly what an injection looks like.
    """
    if not settings.enable_poisoning_resistance:
        return False
    resolved = origin if isinstance(origin, MemoryOrigin) else parse_origin(origin)
    if resolved not in UNTRUSTED_ORIGINS:
        return False
    return confidence < settings.quarantine_confidence_threshold
