"""Domain enums used across models, schemas, and services."""

from __future__ import annotations

import enum


class MemoryType(enum.StrEnum):
    """Classification of memory kind."""

    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class MemoryStatus(enum.StrEnum):
    """Lifecycle status of a canonical memory."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    STALE = "stale"
    ARCHIVED = "archived"
    RETRACTED = "retracted"
    # Conflicts with a higher-confidence memory; retained and linked via a
    # ``contradicts`` edge, but excluded from default retrieval and assembly.
    DISPUTED = "disputed"
    # Written from an untrusted origin below the confidence bar. Stored and
    # reviewable, but never retrieved or assembled until a human releases it.
    QUARANTINED = "quarantined"


class SourceType(enum.StrEnum):
    """Provenance classification for an observation or memory."""

    USER_INPUT = "user_input"
    TOOL_OUTPUT = "tool_output"
    SYSTEM_INFERENCE = "system_inference"
    HUMAN_VERIFIED = "human_verified"
    IMPORTED = "imported"


class MemoryOrigin(enum.StrEnum):
    """*Who* wrote a fact — the trust domain it entered the system from.

    Distinct from :class:`SourceType`, which describes the *kind* of statement
    (an inference, a tool result, a verified fact). Origin answers the security
    question instead: how much should this writer be trusted to assert things?

    Ordered here from most to least trusted. Each origin carries an authority
    ceiling (see :mod:`app.utils.provenance`), so a low-trust writer cannot
    claim high authority and outrank what the user actually said.
    """

    # A human operator/administrator acting on the system directly.
    OPERATOR = "operator"
    # The end user stated this themselves.
    USER = "user"
    # EngramDB itself — distillation, consolidation, reflection.
    SYSTEM = "system"
    # The agent concluded this. The default: it is what an unattributed write is.
    AGENT_INFERENCE = "agent_inference"
    # Returned by a tool the agent invoked.
    TOOL_OUTPUT = "tool_output"
    # Bulk import / migration from another store.
    IMPORTED = "imported"
    # Content from outside the trust boundary: a fetched web page, a third-party
    # API, an uploaded document, another user's message. Anything here may be
    # adversarial — this is the origin prompt-injection arrives through.
    EXTERNAL_INGEST = "external_ingest"


class EventType(enum.StrEnum):
    """Coarse category of events in the append-only log."""

    USER_INPUT = "user_input"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    PLANNER_STEP = "planner_step"
    ACTION_TAKEN = "action_taken"
    MODEL_OUTPUT = "model_output"
    SYSTEM_NOTE = "system_note"


class TaskState(enum.StrEnum):
    """Finite state machine states for tasks."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING_REVIEW = "waiting_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MemoryScope(enum.StrEnum):
    """Visibility scope of a memory record."""

    USER = "user"
    PROJECT = "project"
    TEAM = "team"
    GLOBAL = "global"


class MemoryVisibility(enum.StrEnum):
    """Access-control visibility of a memory (independent of pyramid layer).

    - ``private``    — only the owner can read it.
    - ``team``       — every member of ``team_id`` can read it.
    - ``restricted`` — only principals named in an explicit ACL grant.
    - ``agent``      — only the bound ``agent_id``, within ``team_id``.
    """

    PRIVATE = "private"
    TEAM = "team"
    RESTRICTED = "restricted"
    AGENT = "agent"


class TeamRole(enum.StrEnum):
    """A member's role within a team."""

    ADMIN = "admin"
    MEMBER = "member"


class ACLPrincipal(enum.StrEnum):
    """The kind of principal an ACL grant targets."""

    USER = "user"
    AGENT = "agent"


class MemoryLayer(enum.StrEnum):
    """Distillation layer in the memory pyramid.

    Raw conversation is captured at ``L0`` and refined by the pipeline into
    increasingly abstract, stable layers:

    - ``raw`` (L0): verbatim conversation / event content, high volume, volatile.
    - ``atom`` (L1): a single extracted fact, preference, constraint, or event.
    - ``scenario`` (L2): a knowledge block organised around a project or task.
    - ``persona`` (L3): stable, long-lived profile / cognition about the user.

    Retrieval and context assembly treat higher layers (persona, scenario) as
    prompt-cacheable "bootstrap" context and lower layers (atom, raw) as
    volatile, query-specific recall.
    """

    RAW = "raw"
    ATOM = "atom"
    SCENARIO = "scenario"
    PERSONA = "persona"


# Layers ordered from most stable / abstract to most volatile.
MEMORY_LAYER_STABILITY: dict[MemoryLayer, int] = {
    MemoryLayer.PERSONA: 0,
    MemoryLayer.SCENARIO: 1,
    MemoryLayer.ATOM: 2,
    MemoryLayer.RAW: 3,
}


class LinkType(enum.StrEnum):
    """Relationship type between two memories."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    DERIVED_FROM = "derived_from"
    RELATED_TO = "related_to"


class ObservationStatus(enum.StrEnum):
    """Status of a candidate observation."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    MERGED = "merged"


# ── Task-state transition rules ────────────────────────────────
ALLOWED_TASK_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.PENDING: {TaskState.IN_PROGRESS, TaskState.CANCELLED},
    TaskState.IN_PROGRESS: {
        TaskState.WAITING_REVIEW,
        TaskState.COMPLETED,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.WAITING_REVIEW: {
        TaskState.IN_PROGRESS,
        TaskState.COMPLETED,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.COMPLETED: set(),
    TaskState.FAILED: {TaskState.PENDING},
    TaskState.CANCELLED: {TaskState.PENDING},
}
