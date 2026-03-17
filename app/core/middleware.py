"""Request middleware: request ID, timing, structured logging."""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("agentmemorydb")

# Context variable for request-scoped data
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject a unique X-Request-ID header into every request/response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_ctx.set(req_id)
        request.state.request_id = req_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


class TimingMiddleware(BaseHTTPMiddleware):
    """Measure and log request latency; adds X-Process-Time header."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"

        # Structured log line
        req_id = getattr(request.state, "request_id", "-")
        logger.info(
            "request completed",
            extra={
                "request_id": req_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "elapsed_ms": round(elapsed_ms, 2),
                "client": request.client.host if request.client else "unknown",
            },
        )
        return response


def configure_logging(log_level: str = "INFO") -> None:
    """Set up structured JSON-like logging for the application."""
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | req=%(request_id)s | %(message)s"

    class RequestIDFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if not hasattr(record, "request_id"):
                record.request_id = request_id_ctx.get("")  # type: ignore[attr-defined]
            return True

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(fmt))
    handler.addFilter(RequestIDFilter())

    root_logger = logging.getLogger("agentmemorydb")
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    root_logger.addHandler(handler)
    root_logger.propagate = False

    # Also configure uvicorn access logger
    uv_logger = logging.getLogger("uvicorn.access")
    uv_logger.addFilter(RequestIDFilter())
