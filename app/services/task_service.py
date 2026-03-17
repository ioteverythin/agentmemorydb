"""Task service — state machine + audit trail."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidStateTransitionError, NotFoundError
from app.models.enums import ALLOWED_TASK_TRANSITIONS, TaskState
from app.models.task import Task
from app.models.task_state_transition import TaskStateTransition
from app.repositories.task_repository import TaskRepository
from app.schemas.task import TaskCreate, TaskTransition


class TaskService:
    """Manages task lifecycle with validated state transitions."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = TaskRepository(session)

    async def create_task(self, data: TaskCreate) -> Task:
        """Create a new task in PENDING state."""
        task = Task(
            user_id=data.user_id,
            project_id=data.project_id,
            run_id=data.run_id,
            title=data.title,
            description=data.description,
            priority=data.priority,
            context=data.context,
            state=TaskState.PENDING.value,
        )
        return await self._repo.create(task)

    async def get_task(self, task_id: uuid.UUID) -> Task:
        task = await self._repo.get_by_id(task_id)
        if task is None:
            raise NotFoundError("Task", task_id)
        return task

    async def list_tasks(
        self,
        *,
        user_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        state: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Task]:
        return await self._repo.list_filtered(
            user_id=user_id,
            project_id=project_id,
            state=state,
            limit=limit,
            offset=offset,
        )

    async def transition(self, task_id: uuid.UUID, data: TaskTransition) -> Task:
        """Validate and apply a state transition.

        Raises InvalidStateTransitionError if the transition is not allowed.
        Creates an audit record in task_state_transitions.
        """
        task = await self.get_task(task_id)
        current = TaskState(task.state)
        requested = TaskState(data.to_state)

        allowed = ALLOWED_TASK_TRANSITIONS.get(current, set())
        if requested not in allowed:
            raise InvalidStateTransitionError(current.value, requested.value)

        # Record transition
        transition = TaskStateTransition(
            task_id=task.id,
            from_state=current.value,
            to_state=requested.value,
            reason=data.reason,
            triggered_by=data.triggered_by,
        )
        await self._repo.create_transition(transition)

        # Apply new state
        task.state = requested.value
        return task

    @staticmethod
    def validate_transition(current: str, requested: str) -> bool:
        """Check if a state transition is allowed (pure function, no DB)."""
        try:
            current_state = TaskState(current)
            requested_state = TaskState(requested)
        except ValueError:
            return False
        allowed = ALLOWED_TASK_TRANSITIONS.get(current_state, set())
        return requested_state in allowed
