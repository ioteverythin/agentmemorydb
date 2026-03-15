"""Domain enums used across models, schemas, and services."""

from __future__ import annotations

import enum


class MemoryType(str, enum.Enum):
    """Classification of memory kind."""

    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class MemoryStatus(str, enum.Enum):
    """Lifecycle status of a canonical memory."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    STALE = "stale"
    ARCHIVED = "archived"
    RETRACTED = "retracted"


class SourceType(str, enum.Enum):
    """Provenance classification for an observation or memory."""

    USER_INPUT = "user_input"
    TOOL_OUTPUT = "tool_output"
    SYSTEM_INFERENCE = "system_inference"
    HUMAN_VERIFIED = "human_verified"
    IMPORTED = "imported"


class EventType(str, enum.Enum):
    """Coarse category of events in the append-only log."""

    USER_INPUT = "user_input"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    PLANNER_STEP = "planner_step"
    ACTION_TAKEN = "action_taken"
    MODEL_OUTPUT = "model_output"
    SYSTEM_NOTE = "system_note"


class TaskState(str, enum.Enum):
    """Finite state machine states for tasks."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING_REVIEW = "waiting_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MemoryScope(str, enum.Enum):
    """Visibility scope of a memory record."""

    USER = "user"
    PROJECT = "project"
    TEAM = "team"
    GLOBAL = "global"


class LinkType(str, enum.Enum):
    """Relationship type between two memories."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    DERIVED_FROM = "derived_from"
    RELATED_TO = "related_to"


class ObservationStatus(str, enum.Enum):
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
