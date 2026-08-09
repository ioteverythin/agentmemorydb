"""FastAPI application entrypoint for AgentMemoryDB."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app import __version__
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.metrics import PrometheusMiddleware, metrics_response
from app.core.middleware import RequestIDMiddleware, TimingMiddleware, configure_logging
from app.ws.routes import router as ws_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle hook."""
    # Configure structured logging
    configure_logging(settings.log_level)

    # Startup: initialise embedding provider based on config
    from app.utils.embedding_provider import (
        DummyEmbeddingProvider,
        OpenAIEmbeddingProvider,
        set_embedding_provider,
    )

    provider_name = settings.embedding_provider.lower()
    if provider_name == "openai" and settings.openai_api_key:
        set_embedding_provider(OpenAIEmbeddingProvider())
    elif provider_name == "cohere" and settings.cohere_api_key:
        from app.utils.extra_providers import CohereEmbeddingProvider

        set_embedding_provider(CohereEmbeddingProvider())
    elif provider_name == "ollama":
        from app.utils.extra_providers import OllamaEmbeddingProvider

        set_embedding_provider(
            OllamaEmbeddingProvider(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
            )
        )
    elif provider_name == "sentence-transformers":
        from app.utils.extra_providers import SentenceTransformerProvider

        set_embedding_provider(SentenceTransformerProvider())
    else:
        set_embedding_provider(DummyEmbeddingProvider())

    # Start scheduled maintenance worker as a background task. ``start()`` is
    # an infinite loop, so it must run as a task (not be awaited inline) and be
    # cancelled on shutdown. Use the module singleton so /scheduler endpoints
    # report the running instance rather than a second, idle one.
    import asyncio

    _scheduler = None
    _scheduler_task: asyncio.Task | None = None
    if settings.enable_scheduler:
        from app.workers.scheduler import get_scheduler

        _scheduler = get_scheduler()
        _scheduler_task = asyncio.create_task(_scheduler.start())

    yield

    # Shutdown: stop scheduler and cancel its task.
    if _scheduler is not None:
        await _scheduler.stop()
    if _scheduler_task is not None:
        _scheduler_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _scheduler_task

    # Shutdown: dispose the connection pool.
    from app.db.session import engine

    await engine.dispose()


def create_app() -> FastAPI:
    """Application factory."""
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=("SQL-native, auditable, event-sourced memory + state backend for agentic AI."),
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url="/redoc" if settings.enable_docs else None,
        lifespan=lifespan,
    )

    # ── Middleware stack (order matters: outermost first) ────────
    # A wildcard origin with credentials is rejected by browsers and unsafe, so
    # never emit that combination. Credentials are only enabled when explicit
    # origins are configured.
    origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
    allow_credentials = settings.cors_allow_credentials and "*" not in origins
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestIDMiddleware)
    application.add_middleware(TimingMiddleware)

    if settings.enable_metrics:
        application.add_middleware(PrometheusMiddleware)

    # ── Routes ──────────────────────────────────────────────────
    application.include_router(api_router, prefix="/api/v1")

    # ── WebSocket (real-time memory events) ─────────────────────
    if settings.enable_websocket:
        application.include_router(ws_router)

    # ── Memory Explorer UI ──────────────────────────────────────
    if settings.enable_explorer:
        import pathlib

        from fastapi.staticfiles import StaticFiles

        static_dir = pathlib.Path(__file__).parent / "static" / "explorer"
        if static_dir.exists():
            application.mount(
                "/explorer", StaticFiles(directory=str(static_dir), html=True), name="explorer"
            )

    # ── Prometheus metrics endpoint ─────────────────────────────
    if settings.enable_metrics:

        @application.get("/metrics", include_in_schema=False)
        async def prometheus_metrics() -> Response:
            return metrics_response()

    return application


app = create_app()
