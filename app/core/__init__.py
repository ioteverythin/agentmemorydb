"""Application settings loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for AgentMemoryDB."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Application ──────────────────────────────────────────────
    app_name: str = "AgentMemoryDB"
    environment: str = "development"
    log_level: str = "INFO"
    enable_docs: bool = True

    # ── Database ─────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://agentmem:agentmem_secret@localhost:5432/agentmemorydb"
    database_echo: bool = False

    # ── Embedding ────────────────────────────────────────────────
    embedding_dimension: int = 1536
    vector_index_lists: int = 100

    # ── Vector index (HNSW recommended, IVFFlat still supported) ─
    vector_index_type: str = "hnsw"  # "hnsw" or "ivfflat"
    hnsw_m: int = 16  # max bi-directional links per node
    hnsw_ef_construction: int = 64  # size of dynamic candidate list during build
    hnsw_ef_search: int = 40  # size of dynamic candidate list during search

    # ── Retrieval ────────────────────────────────────────────────
    default_top_k: int = 10

    # ── Scoring weights (must sum to 1.0) ────────────────────────
    score_weight_vector: float = 0.45
    score_weight_recency: float = 0.20
    score_weight_importance: float = 0.15
    score_weight_authority: float = 0.10
    score_weight_confidence: float = 0.10

    # ── Authentication ────────────────────────────────────────
    require_auth: bool = False  # Set True in production

    # ── Optional OpenAI ──────────────────────────────────────
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"

    # ── Optional Cohere ──────────────────────────────────────
    cohere_api_key: str | None = None

    # ── Optional Ollama ──────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "nomic-embed-text"

    # ── Embedding provider selection ─────────────────────────
    embedding_provider: str = "dummy"  # dummy | openai | cohere | sentence-transformers | ollama

    # ── Full-text search ─────────────────────────────────────
    enable_fulltext_search: bool = True
    fulltext_weight: float = 0.1  # weight in hybrid scoring when FTS is used

    # ── Webhooks ─────────────────────────────────────────────
    enable_webhooks: bool = True

    # ── Metrics ──────────────────────────────────────────────
    enable_metrics: bool = True

    # ── Access tracking ──────────────────────────────────────
    enable_access_tracking: bool = True
    access_boost_factor: float = 0.05
    access_boost_window_hours: int = 168  # 7 days

    # ── WebSocket ────────────────────────────────────────────
    enable_websocket: bool = True

    # ── MCP Server ───────────────────────────────────────────
    enable_mcp: bool = True

    # ── Memory Explorer UI ───────────────────────────────────
    enable_explorer: bool = True

    # ── Scheduled Maintenance ────────────────────────────────
    enable_scheduler: bool = True
    scheduler_consolidation_interval: int = 3600  # seconds between runs
    scheduler_archive_interval: int = 7200
    scheduler_recency_interval: int = 1800
    scheduler_cleanup_interval: int = 3600
    scheduler_prune_interval: int = 86400
    scheduler_stale_threshold_days: int = 90  # archive memories older than
    scheduler_access_log_retention_days: int = 90  # prune access logs older than
    scheduler_enable_consolidation: bool = True
    scheduler_enable_archive: bool = True
    scheduler_enable_recency: bool = True
    scheduler_enable_cleanup: bool = True
    scheduler_enable_prune: bool = True

    # ── Row Level Security ───────────────────────────────────
    enable_rls: bool = False  # Enable after running 004_add_rls migration

    # ── Data Masking (PII Compliance) ────────────────────────
    enable_data_masking: bool = False  # Set True to mask PII before persistence
    masking_patterns: str = (
        "email,phone,ssn,credit_card,ip_address"  # comma-separated built-in patterns
    )
    masking_log_detections: bool = True  # Write audit log for every masking action
    masking_custom_patterns: str | None = None  # JSON array of {name, regex, token} dicts


settings = Settings()
