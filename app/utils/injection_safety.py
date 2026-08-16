"""Sanitisation for memory content injected into LLM prompts.

Stored memory is untrusted: it originates from prior conversations, tool
output, or imported data, any of which may contain text crafted to break out
of the delimiter that frames it and issue instructions to the model (stored
prompt injection). When we assemble memories into a context block we therefore:

1. Neutralise closing-delimiter forgery — any substring that looks like the
   fence/tag we use to wrap a memory is defanged so stored content cannot end
   the block early and have following text treated as trusted.
2. Strip common instruction-injection lead-ins ("ignore previous
   instructions", "system:", tool-call fences) at the start of lines.
3. Bound length so a single memory cannot dominate the context window.

This is defence-in-depth, not a guarantee: the assembled block is always
labelled as untrusted data in the surrounding template so the model treats it
as reference material, never as commands.
"""

from __future__ import annotations

import re

# Reserved delimiter tokens used by the context-assembly template. Any
# occurrence inside memory content is escaped so it cannot forge a boundary.
_RESERVED_TOKENS = (
    "<untrusted-memory>",
    "</untrusted-memory>",
    "<memory",
    "</memory>",
    "<memory-context>",
    "</memory-context>",
)

# Line-leading injection lead-ins we defuse by prefixing a zero-width marker.
_INJECTION_LEADINS = re.compile(
    r"(?im)^\s*(ignore\s+(all\s+)?(previous|prior|above)\s+instructions"
    r"|disregard\s+(all\s+)?(previous|prior|above)"
    r"|system\s*:"
    r"|assistant\s*:"
    r"|you\s+are\s+now"
    r"|new\s+instructions?\s*:)",
)


def sanitize_injected_text(text: str, *, max_chars: int = 2000) -> str:
    """Return ``text`` made safe to embed inside an untrusted-memory fence.

    Escapes reserved delimiter tokens, defuses line-leading injection lead-ins,
    collapses control characters, and truncates to ``max_chars``.
    """
    if not text:
        return ""

    cleaned = text.replace("\x00", "")
    # Escape reserved delimiters (case-insensitive) by breaking the angle bracket.
    for token in _RESERVED_TOKENS:
        pattern = re.compile(re.escape(token), re.IGNORECASE)
        cleaned = pattern.sub(lambda m: m.group(0).replace("<", "‹").replace(">", "›"), cleaned)

    # Defuse instruction lead-ins so they read as quoted text, not commands.
    cleaned = _INJECTION_LEADINS.sub(lambda m: "[quoted] " + m.group(0).lstrip(), cleaned)

    if len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 1].rstrip() + "…"

    return cleaned
