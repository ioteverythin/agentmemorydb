"""Unit tests for task state transition validation."""

from __future__ import annotations

import pytest

from app.models.enums import TaskState
from app.services.task_service import TaskService


@pytest.mark.unit
class TestTaskStateTransitions:
    """Pure-function tests for allowed/disallowed transitions."""

    @pytest.mark.parametrize(
        "current,requested,expected",
        [
            # Valid transitions
            ("pending", "in_progress", True),
            ("pending", "cancelled", True),
            ("in_progress", "waiting_review", True),
            ("in_progress", "completed", True),
            ("in_progress", "failed", True),
            ("in_progress", "cancelled", True),
            ("waiting_review", "in_progress", True),
            ("waiting_review", "completed", True),
            ("waiting_review", "failed", True),
            ("waiting_review", "cancelled", True),
            ("failed", "pending", True),
            ("cancelled", "pending", True),
            # Invalid transitions
            ("pending", "completed", False),
            ("pending", "failed", False),
            ("pending", "waiting_review", False),
            ("completed", "pending", False),
            ("completed", "in_progress", False),
            ("completed", "failed", False),
            ("failed", "completed", False),
            ("cancelled", "completed", False),
        ],
    )
    def test_validate_transition(self, current: str, requested: str, expected: bool):
        result = TaskService.validate_transition(current, requested)
        assert result is expected, (
            f"Transition {current} -> {requested}: expected {expected}, got {result}"
        )

    def test_invalid_state_name_returns_false(self):
        assert TaskService.validate_transition("bogus", "pending") is False
        assert TaskService.validate_transition("pending", "bogus") is False
