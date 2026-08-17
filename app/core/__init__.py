"""Application settings loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for EngramDB."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Application ──────────────────────────────────────────────
    app_name: str = "EngramDB"
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

    # ── Forgetting: decay & reconsolidation (Ebbinghaus-style) ───
    # Importance decays exponentially since last access; frequently-recalled
    # memories are boosted on retrieval, so use resists decay. Pinned memories
    # are never decayed or archived.
    enable_decay: bool = False
    decay_half_life_hours: float = 720.0  # 30 days
    decay_floor: float = 0.05
    scheduler_decay_interval: int = 21600  # 6h
    scheduler_enable_decay: bool = True
    enable_reconsolidation: bool = False
    reconsolidation_boost: float = 0.02

    # ── LLM provider (optional; powers contradiction + reflection) ─
    llm_provider: str = "none"  # none | openai
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None  # set for an OpenAI-compatible gateway
    llm_temperature: float = 0.0
    llm_timeout_seconds: float = 30.0

    # ── Contradiction detection ──────────────────────────────────
    enable_contradiction_detection: bool = False
    contradiction_strategy: str = "heuristic"  # heuristic | llm
    contradiction_similarity_threshold: float = 0.85
    contradiction_candidate_top_k: int = 5

    # ── Temporal validity (bitemporal facts) ─────────────────────
    # When True, retrieval defaults to *currently-valid* facts only
    # (``valid_to IS NULL``) and honours ``as_of`` for point-in-time queries.
    # When False (default) behaviour is byte-identical to pre-migration:
    # ``valid_to IS NULL OR valid_to > now()``.
    enable_temporal_validity: bool = False

    # ── Retrieval ────────────────────────────────────────────────
    default_top_k: int = 10
    # Over-fetch multiplier: how many raw candidates to pull per requested
    # result before composite re-ranking. Larger values let high-importance /
    # recent memories outside the top-k vector neighbours still surface.
    retrieval_overfetch_multiplier: int = 4
    # Reciprocal-rank-fusion constant (BM25/FTS + vector). Higher = flatter.
    rrf_k: int = 60

    # ── Scoring weights (must sum to 1.0) ────────────────────────
    score_weight_vector: float = 0.45
    score_weight_recency: float = 0.20
    score_weight_importance: float = 0.15
    score_weight_authority: float = 0.10
    score_weight_confidence: float = 0.10

    # ── Authentication ────────────────────────────────────────
    require_auth: bool = False  # Set True in production
    # When True (and require_auth is on), a request's body/query user_id must
    # match the authenticated API key's owner — a key for user A cannot read or
    # mutate user B's memories. This is the tenant-isolation boundary.
    enforce_tenant_isolation: bool = True

    # ── CORS ──────────────────────────────────────────────────
    # Comma-separated list of allowed origins. "*" is only honoured with
    # credentials disabled (a wildcard + credentials is rejected by browsers
    # and unsafe). Set explicit origins in production to allow credentials.
    cors_allow_origins: str = "*"
    cors_allow_credentials: bool = False

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

    # ── Lifecycle events (webhooks + WebSocket on memory changes) ─
    # Master switch for firing memory.created/updated/archived/etc. events.
    # When off, no webhooks or WebSocket broadcasts are emitted on writes.
    emit_lifecycle_events: bool = True

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
    # Expose the irreversible `forget_memory` tool over MCP. Off by default:
    # an agent should not be able to hard-delete data unless deliberately
    # allowed to, and even then the key needs the `erase` scope.
    mcp_enable_forget: bool = False

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
    scheduler_distillation_interval: int = 21600  # 6h — roll atoms up the pyramid
    scheduler_enable_consolidation: bool = True
    scheduler_enable_archive: bool = True
    scheduler_enable_recency: bool = True
    scheduler_enable_cleanup: bool = True
    scheduler_enable_prune: bool = True
    scheduler_enable_distillation: bool = True

    # ── Distillation (self-filling pyramid: atom → scenario → persona) ─
    distillation_min_group_size: int = 2  # atoms per topic before a scenario forms
    distillation_scenario_char_budget: int = 1200
    distillation_persona_char_budget: int = 1500
    distillation_min_scenarios_for_persona: int = 1

    # ── Forgetting (importance/access-aware archival) ────────
    forgetting_retention_threshold: float = 0.35  # archive below this
    forget_weight_recency: float = 0.4
    forget_weight_importance: float = 0.4
    forget_weight_access: float = 0.2
    forgetting_min_age_days: int = 14  # never archive memories younger than this
    forgetting_access_saturation: int = 20
    forgetting_exempt_layers: str = "persona,scenario"  # distilled layers are kept

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
