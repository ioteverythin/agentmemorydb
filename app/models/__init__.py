"""Model registry — import all models so Alembic and Base.metadata see them."""

from app.models.agent_run import AgentRun
from app.models.api_key import APIKey
from app.models.artifact import ArtifactMetadata
from app.models.enums import (
    ALLOWED_TASK_TRANSITIONS,
    EventType,
    LinkType,
    MemoryScope,
    MemoryStatus,
    MemoryType,
    ObservationStatus,
    SourceType,
    TaskState,
)
from app.models.event import Event
from app.models.masking_log import MaskingLog
from app.models.memory import Memory
from app.models.memory_access_log import MemoryAccessLog
from app.models.memory_link import MemoryLink
from app.models.memory_version import MemoryVersion
from app.models.observation import Observation
from app.models.project import Project
from app.models.retrieval_log import RetrievalLog, RetrievalLogItem
from app.models.task import Task
from app.models.task_state_transition import TaskStateTransition
from app.models.user import User
from app.models.webhook import Webhook, WebhookDelivery

__all__ = [
    "ALLOWED_TASK_TRANSITIONS",
    "APIKey",
    "AgentRun",
    "ArtifactMetadata",
    "Event",
    "EventType",
    "LinkType",
    "MaskingLog",
    "Memory",
    "MemoryAccessLog",
    "MemoryLink",
    "MemoryScope",
    "MemoryStatus",
    # Enums
    "MemoryType",
    "MemoryVersion",
    "Observation",
    "ObservationStatus",
    "Project",
    "RetrievalLog",
    "RetrievalLogItem",
    "SourceType",
    "Task",
    "TaskState",
    "TaskStateTransition",
    "User",
    "Webhook",
    "WebhookDelivery",
]
