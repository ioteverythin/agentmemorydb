"""Model registry — import all models so Alembic and Base.metadata see them."""

from app.models.user import User
from app.models.project import Project
from app.models.agent_run import AgentRun
from app.models.event import Event
from app.models.observation import Observation
from app.models.memory import Memory
from app.models.memory_version import MemoryVersion
from app.models.memory_link import MemoryLink
from app.models.task import Task
from app.models.task_state_transition import TaskStateTransition
from app.models.retrieval_log import RetrievalLog, RetrievalLogItem
from app.models.artifact import ArtifactMetadata
from app.models.api_key import APIKey
from app.models.webhook import Webhook, WebhookDelivery
from app.models.memory_access_log import MemoryAccessLog
from app.models.masking_log import MaskingLog
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

__all__ = [
    "User",
    "Project",
    "AgentRun",
    "Event",
    "Observation",
    "Memory",
    "MemoryVersion",
    "MemoryLink",
    "Task",
    "TaskStateTransition",
    "RetrievalLog",
    "RetrievalLogItem",
    "ArtifactMetadata",
    "APIKey",
    "Webhook",
    "WebhookDelivery",
    "MemoryAccessLog",
    "MaskingLog",
    # Enums
    "MemoryType",
    "MemoryStatus",
    "SourceType",
    "EventType",
    "TaskState",
    "MemoryScope",
    "LinkType",
    "ObservationStatus",
    "ALLOWED_TASK_TRANSITIONS",
]
