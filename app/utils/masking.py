"""PII detection and data masking engine.

Write-time masking with full-replacement strategy.
Detects PII patterns in text and replaces them with type tokens
(e.g. ``[EMAIL]``, ``[PHONE]``) *before* persistence.

All detection is regex-based and runs synchronously — no external
API calls.  Custom patterns can be added via ``MASKING_CUSTOM_PATTERNS``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ── Built-in PII patterns ──────────────────────────────────────────
# Each pattern has: name, compiled regex, replacement token.

@dataclass(frozen=True, slots=True)
class PIIPattern:
    """Specification for a single PII detection pattern."""

    name: str
    regex: re.Pattern[str]
    token: str


# Order matters — more specific patterns should come first to avoid
# partial matches (e.g. SSN before generic number sequences).

_BUILTIN_PATTERNS: dict[str, PIIPattern] = {
    "ssn": PIIPattern(
        name="ssn",
        regex=re.compile(
            r"\b\d{3}[-–]\d{2}[-–]\d{4}\b"
        ),
        token="[SSN]",
    ),
    "credit_card": PIIPattern(
        name="credit_card",
        regex=re.compile(
            # Visa, MC, Amex, Discover — with optional separators
            r"\b(?:\d{4}[-– ]?){3}\d{1,4}\b"
        ),
        token="[CREDIT_CARD]",
    ),
    "email": PIIPattern(
        name="email",
        regex=re.compile(
            r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
        ),
        token="[EMAIL]",
    ),
    "phone": PIIPattern(
        name="phone",
        regex=re.compile(
            # International / US formats: +1-555-123-4567, (555) 123-4567, 555.123.4567
            r"(?<!\d)"  # negative lookbehind — avoid matching inside long numbers
            r"(?:\+\d{1,3}[-.\s]?)?"  # optional country code
            r"(?:\(?\d{3}\)?[-.\s]?)"  # area code
            r"\d{3}[-.\s]?\d{4}"
            r"(?!\d)"  # negative lookahead
        ),
        token="[PHONE]",
    ),
    "ip_address": PIIPattern(
        name="ip_address",
        regex=re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
        ),
        token="[IP_ADDRESS]",
    ),
    "us_passport": PIIPattern(
        name="us_passport",
        regex=re.compile(r"\b[A-Z]\d{8}\b"),
        token="[PASSPORT]",
    ),
    "date_of_birth": PIIPattern(
        name="date_of_birth",
        regex=re.compile(
            # Matches common DOB patterns preceded by keywords
            r"(?i)(?:dob|date\s*of\s*birth|born(?:\s+on)?)\s*[:=]?\s*"
            r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{4}[/\-]\d{1,2}[/\-]\d{1,2})"
        ),
        token="[DOB]",
    ),
}


@dataclass
class MaskingResult:
    """Output of a masking operation on a single text field."""

    original_text: str
    masked_text: str
    detections: list[Detection] = field(default_factory=list)
    was_modified: bool = False

    @property
    def patterns_detected(self) -> list[str]:
        return list({d.pattern_name for d in self.detections})


@dataclass(frozen=True, slots=True)
class Detection:
    """A single PII match within a text."""

    pattern_name: str
    token: str
    start: int
    end: int
    matched_text: str  # kept only in-memory for audit hash, never persisted


# ── Engine ──────────────────────────────────────────────────────────

class PIIMaskingEngine:
    """Stateless masking engine.

    Initialise with the list of pattern names to activate and optional
    custom patterns, then call :meth:`mask_text` on any string.
    """

    def __init__(
        self,
        enabled_patterns: list[str] | None = None,
        custom_patterns: list[dict[str, str]] | None = None,
    ) -> None:
        self._patterns: list[PIIPattern] = []

        # Add built-in patterns that are enabled
        if enabled_patterns:
            for name in enabled_patterns:
                if name in _BUILTIN_PATTERNS:
                    self._patterns.append(_BUILTIN_PATTERNS[name])

        # Add custom regex patterns
        if custom_patterns:
            for cp in custom_patterns:
                self._patterns.append(
                    PIIPattern(
                        name=cp["name"],
                        regex=re.compile(cp["regex"]),
                        token=cp.get("token", f"[{cp['name'].upper()}]"),
                    )
                )

    @property
    def active_patterns(self) -> list[str]:
        return [p.name for p in self._patterns]

    def mask_text(self, text: str) -> MaskingResult:
        """Scan *text* for PII and replace all matches with tokens.

        Returns a :class:`MaskingResult` with the masked text,
        a list of detections, and a flag indicating whether any
        modifications were made.
        """
        if not text or not self._patterns:
            return MaskingResult(
                original_text=text,
                masked_text=text,
                was_modified=False,
            )

        detections: list[Detection] = []

        # Collect all matches first (to record original spans)
        all_matches: list[tuple[int, int, str, PIIPattern]] = []
        for pattern in self._patterns:
            for m in pattern.regex.finditer(text):
                all_matches.append((m.start(), m.end(), m.group(), pattern))

        if not all_matches:
            return MaskingResult(
                original_text=text,
                masked_text=text,
                was_modified=False,
            )

        # Sort by start position (earlier first), then longer match first
        all_matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))

        # Deduplicate overlapping matches — keep the first (longest) one
        merged: list[tuple[int, int, str, PIIPattern]] = []
        for start, end, matched, pattern in all_matches:
            if merged and start < merged[-1][1]:
                continue  # overlaps with previous kept match
            merged.append((start, end, matched, pattern))

        # Build masked text + detection records
        parts: list[str] = []
        prev_end = 0
        for start, end, matched, pattern in merged:
            parts.append(text[prev_end:start])
            parts.append(pattern.token)
            detections.append(
                Detection(
                    pattern_name=pattern.name,
                    token=pattern.token,
                    start=start,
                    end=end,
                    matched_text=matched,
                )
            )
            prev_end = end
        parts.append(text[prev_end:])

        masked_text = "".join(parts)
        return MaskingResult(
            original_text=text,
            masked_text=masked_text,
            detections=detections,
            was_modified=True,
        )

    def mask_dict(self, data: dict[str, Any], fields: list[str] | None = None) -> dict[str, list[Detection]]:
        """Mask string values within a dictionary in-place.

        Parameters
        ----------
        data:
            The dictionary whose values should be scanned.
        fields:
            If provided, only these keys are scanned.  Otherwise all
            top-level string values are scanned.

        Returns a mapping of field_name → list of detections.
        """
        all_detections: dict[str, list[Detection]] = {}
        keys = fields if fields else [k for k, v in data.items() if isinstance(v, str)]

        for key in keys:
            if key not in data or not isinstance(data[key], str):
                continue
            result = self.mask_text(data[key])
            if result.was_modified:
                data[key] = result.masked_text
                all_detections[key] = result.detections

        return all_detections


def get_default_engine() -> PIIMaskingEngine:
    """Build an engine from current application settings.

    This is a convenience factory; callers can also construct
    :class:`PIIMaskingEngine` directly.
    """
    from app.core import settings

    if not settings.enable_data_masking:
        return PIIMaskingEngine(enabled_patterns=[])

    pattern_names = [
        p.strip() for p in settings.masking_patterns.split(",") if p.strip()
    ]

    custom: list[dict[str, str]] | None = None
    if settings.masking_custom_patterns:
        import json
        try:
            custom = json.loads(settings.masking_custom_patterns)
        except (json.JSONDecodeError, TypeError):
            custom = None

    return PIIMaskingEngine(
        enabled_patterns=pattern_names,
        custom_patterns=custom,
    )
