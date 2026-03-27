"""Lightweight regex-based entity extractor.

Inspired by MAGMA's Knowledge Graph Encoder which builds structured
entity/relation indexes alongside raw memory content.  Rather than
requiring a full NER pipeline or an external model, this module uses
compiled regex patterns to extract the most common structured entities
from free-text memory content at write time.

Extracted entities are stored in ``payload["__entities__"]`` so they can
be filtered and faceted during retrieval without re-scanning the text:

    payload = {
        "__entities__": {
            "emails":   ["alice@example.com"],
            "urls":     ["https://api.example.com/v1"],
            "mentions": ["@alice", "@bob"],
            "dates":    ["2024-01-15", "March 3rd"],
            "names":    ["Alice Smith", "Project Phoenix"],
            "numbers":  ["42 ms", "3.5 GB", "$120"],
        }
    }

Usage::

    from app.utils.entity_extractor import extract_entities

    entities = extract_entities("Meeting with Alice Smith on 2024-03-15 about Project Phoenix.")
    # {"names": ["Alice Smith", "Project Phoenix"], "dates": ["2024-03-15"], ...}
"""

from __future__ import annotations

import re

# ── Compiled patterns (module-level for zero per-call overhead) ──

_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

_URL_RE = re.compile(
    r"https?://[^\s\]\"')>]+"
)

_MENTION_RE = re.compile(
    r"@[A-Za-z][A-Za-z0-9_]{1,30}\b"
)

# ISO dates: 2024-01-15
_DATE_ISO_RE = re.compile(
    r"\b\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\b"
)

# Written dates: "March 3rd", "15 January 2024", "Jan 7"
_DATE_WRITTEN_RE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?|\b\d{1,2}\s+"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"(?:,?\s+\d{4})?\b",
    re.IGNORECASE,
)

# Numbers with units: "42 ms", "3.5 GB", "$120", "95%"
_NUMBER_UNIT_RE = re.compile(
    r"\$[\d,]+(?:\.\d+)?|\b\d+(?:\.\d+)?\s*(?:ms|s|GB|MB|KB|TB|GHz|MHz|"
    r"px|em|rem|vw|vh|rpm|bpm|kg|lb|g|m|km|mi|°C|°F|%|K|M|B)\b"
)

# Proper-noun phrases: 2+ consecutive Title Case words (excludes all-caps acronyms
# and common English stop-words at the start of sentences)
_PROPER_NOUN_RE = re.compile(
    r"\b(?!(?:The|A|An|In|On|At|By|To|Of|And|Or|But|Is|Are|Was|Were|"
    r"Has|Have|Had|Will|Would|Could|Should|May|Might|Must|Shall)\b)"
    r"[A-Z][a-z]{1,30}(?:\s+[A-Z][a-z]{1,30}){1,4}\b"
)

# Single-word hashtags
_HASHTAG_RE = re.compile(r"#[A-Za-z][A-Za-z0-9_]{2,29}\b")


def extract_entities(text: str) -> dict[str, list[str]]:
    """Return a dict of entity lists extracted from *text*.

    All lists are de-duplicated and order-preserving.  Empty lists are
    omitted so the resulting dict stays compact.

    Args:
        text: Raw memory content string.

    Returns:
        Dict with zero or more of the keys:
        ``emails``, ``urls``, ``mentions``, ``dates``, ``names``,
        ``numbers``, ``hashtags``.
    """
    result: dict[str, list[str]] = {}

    def _dedup(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            key = item.strip().lower()
            if key not in seen:
                seen.add(key)
                out.append(item.strip())
        return out

    emails = _dedup(_EMAIL_RE.findall(text))
    if emails:
        result["emails"] = emails

    urls = _dedup(_URL_RE.findall(text))
    if urls:
        result["urls"] = urls

    mentions = _dedup(_MENTION_RE.findall(text))
    if mentions:
        result["mentions"] = mentions

    dates = _dedup(_DATE_ISO_RE.findall(text) + _DATE_WRITTEN_RE.findall(text))
    if dates:
        result["dates"] = dates

    numbers = _dedup(_NUMBER_UNIT_RE.findall(text))
    if numbers:
        result["numbers"] = numbers

    hashtags = _dedup(_HASHTAG_RE.findall(text))
    if hashtags:
        result["hashtags"] = hashtags

    # Proper-noun names: strip any that are already captured as emails/urls
    blocked = {e.lower() for e in emails} | {u.lower() for u in urls}
    names = _dedup(
        [m for m in _PROPER_NOUN_RE.findall(text) if m.lower() not in blocked]
    )
    if names:
        result["names"] = names

    return result


def merge_entities(
    existing: dict | None,
    new_entities: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Merge *new_entities* into *existing* payload ``__entities__`` block.

    Preserves manually-added entities while updating auto-extracted ones.

    Args:
        existing: Current ``payload["__entities__"]`` value, or ``None``.
        new_entities: Freshly extracted entities from the new content.

    Returns:
        Merged dict ready to be stored back in ``payload["__entities__"]``.
    """
    if not existing:
        return new_entities
    merged: dict[str, list[str]] = dict(existing)
    for key, values in new_entities.items():
        merged_set = dict.fromkeys(merged.get(key, []))
        for v in values:
            merged_set[v] = None
        merged[key] = list(merged_set)
    return merged
