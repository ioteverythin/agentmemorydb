"""Provenance schemas — trust policy and quarantine review."""

from __future__ import annotations

from pydantic import BaseModel


class OriginPolicyResponse(BaseModel):
    """The active write-trust policy."""

    enabled: bool
    quarantine_confidence_threshold: float
    # origin → highest authority_level that origin may claim
    authority_ceilings: dict[str, int]
    # Origins eligible for quarantine when their confidence is below the bar.
    untrusted_origins: list[str]


class QuarantineReviewRequest(BaseModel):
    """A human decision on a quarantined memory."""

    approve: bool
    reviewer: str | None = None
