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


class SourceType(enum.StrEnum):
    """Provenance classification for an observation or memory."""

    USER_INPUT = "user_input"
    TOOL_OUTPUT = "tool_output"
    SYSTEM_INFERENCE = "system_inference"
    HUMAN_VERIFIED = "human_verified"
    IMPORTED = "imported"


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
