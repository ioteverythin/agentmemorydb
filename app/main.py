"""FastAPI application entrypoint for AgentMemoryDB."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app import __version__
from app.core.config import settings
from app.core.middleware import RequestIDMiddleware, TimingMiddleware, configure_logging
from app.core.metrics import PrometheusMiddleware, metrics_response
from app.api.v1.router import api_router
from app.ws.routes import router as ws_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle hook."""
    # Configure structured logging
    configure_logging(settings.log_level)

    # Startup: initialise embedding provider based on config
    from app.utils.embedding_provider import set_embedding_provider, DummyEmbeddingProvider, OpenAIEmbeddingProvider

    provider_name = settings.embedding_provider.lower()
    if provider_name == "openai" and settings.openai_api_key:
        set_embedding_provider(OpenAIEmbeddingProvider())
    elif provider_name == "cohere" and settings.cohere_api_key:
        from app.utils.extra_providers import CohereEmbeddingProvider
        set_embedding_provider(CohereEmbeddingProvider())
    elif provider_name == "ollama":
        from app.utils.extra_providers import OllamaEmbeddingProvider
        set_embedding_provider(OllamaEmbeddingProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
        ))
    elif provider_name == "sentence-transformers":
        from app.utils.extra_providers import SentenceTransformerProvider
        set_embedding_provider(SentenceTransformerProvider())
    else:
        set_embedding_provider(DummyEmbeddingProvider())

    # Start scheduled maintenance worker
    _scheduler = None
    if settings.enable_scheduler:
        from app.workers.scheduler import MaintenanceScheduler
        _scheduler = MaintenanceScheduler()
        _scheduler.start()

    yield

    # Shutdown: stop scheduler
    if _scheduler is not None:
        _scheduler.stop()

    # Shutdown: dispose the connection pool.
    from app.db.session import engine
    await engine.dispose()


def create_app() -> FastAPI:
    """Application factory."""
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "SQL-native, auditable, event-sourced memory + state backend for agentic AI."
        ),
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url="/redoc" if settings.enable_docs else None,
        lifespan=lifespan,
    )

    # ── Middleware stack (order matters: outermost first) ────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
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
            application.mount("/explorer", StaticFiles(directory=str(static_dir), html=True), name="explorer")

    # ── Prometheus metrics endpoint ─────────────────────────────
    if settings.enable_metrics:
        @application.get("/metrics", include_in_schema=False)
        async def prometheus_metrics() -> Response:
            return metrics_response()

    return application


app = create_app()
