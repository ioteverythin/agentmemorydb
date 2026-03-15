"""Standalone PII masking engine for the embedded client.

Self-contained — no dependency on the server's ``app`` package.
Provides the same 7 built-in patterns as the server masking module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PIIPattern:
    """A named regex + replacement token."""

    name: str
    regex: str
    token: str


# ── Built-in patterns (same as server) ──────────────────────────────

_BUILTIN_PATTERNS: list[PIIPattern] = [
    PIIPattern(
        "email",
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
        "[EMAIL]",
    ),
    PIIPattern(
        "phone",
        r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}",
        "[PHONE]",
    ),
    PIIPattern("ssn", r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]"),
    PIIPattern("credit_card", r"\b(?:\d[ -]*?){13,19}\b", "[CREDIT_CARD]"),
    PIIPattern(
        "ip_address", r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[IP_ADDRESS]"
    ),
    PIIPattern("us_passport", r"\b[A-Z]\d{8}\b", "[PASSPORT]"),
    PIIPattern(
        "date_of_birth",
        r"(?i)(?:dob|date of birth|birth\s*date)\s*[:\-]?\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}",
        "[DOB]",
    ),
]


# ── Result container ────────────────────────────────────────────────


@dataclass
class MaskingResult:
    """Output of a masking operation."""

    original_text: str
    masked_text: str
    detections: list[dict] = field(default_factory=list)

    @property
    def was_masked(self) -> bool:
        return len(self.detections) > 0


# ── Engine ──────────────────────────────────────────────────────────


class PIIMaskingEngine:
    """Regex-based PII detection and full-replacement masking."""

    def __init__(self, patterns: list[PIIPattern] | None = None) -> None:
        self._patterns = patterns if patterns is not None else list(_BUILTIN_PATTERNS)

    def mask_text(self, text: str) -> MaskingResult:
        """Scan *text* for PII and replace each match with its token."""
        detections: list[dict] = []

        for pat in self._patterns:
            for m in re.finditer(pat.regex, text):
                detections.append(
                    {
                        "pattern": pat.name,
                        "start": m.start(),
                        "end": m.end(),
                        "token": pat.token,
                    }
                )

        if not detections:
            return MaskingResult(original_text=text, masked_text=text)

        # Resolve overlaps: earlier start wins; ties break by longer span
        detections.sort(key=lambda d: (d["start"], -(d["end"] - d["start"])))

        filtered: list[dict] = []
        last_end = -1
        for d in detections:
            if d["start"] >= last_end:
                filtered.append(d)
                last_end = d["end"]

        # Rebuild masked string
        parts: list[str] = []
        pos = 0
        for d in filtered:
            parts.append(text[pos : d["start"]])
            parts.append(d["token"])
            pos = d["end"]
        parts.append(text[pos:])

        return MaskingResult(
            original_text=text,
            masked_text="".join(parts),
            detections=filtered,
        )
