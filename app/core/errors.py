"""Structured error handling for the API layer."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel


# ── Structured error response body ──────────────────────────────
class ErrorDetail(BaseModel):
    """Standard error payload returned to clients."""

    error: str
    detail: str | None = None
    field: str | None = None


class ErrorResponse(BaseModel):
    """Wrapper returned on 4xx / 5xx."""

    errors: list[ErrorDetail]


# ── Convenience exceptions ──────────────────────────────────────
class NotFoundError(HTTPException):
    def __init__(self, resource: str, identifier: Any = None) -> None:
        detail = f"{resource} not found"
        if identifier is not None:
            detail = f"{resource} '{identifier}' not found"
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class ConflictError(HTTPException):
    def __init__(self, detail: str = "Resource conflict") -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class ValidationError(HTTPException):
    def __init__(self, detail: str = "Validation failed", field: str | None = None) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )
        self.field = field


class InvalidStateTransitionError(HTTPException):
    def __init__(self, current: str, requested: str) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot transition from '{current}' to '{requested}'",
        )
