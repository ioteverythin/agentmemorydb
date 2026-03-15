# AgentMemoryDB — Architecture

> SQL-native, auditable, event-sourced memory + state backend for agentic AI.

---

## High-Level Overview

```
┌──────────────┐    ┌──────────────────────────────────┐
│  Agent / App  │───▶│    Middleware Stack              │
│  SDK / CLI    │    │  RequestID · Timing · Prometheus │
└──────────────┘    │  CORS · API-Key Auth             │
                    └──────────┬───────────────────────┘
                               │
                    ┌──────────▼───────────────────────┐
                    │       FastAPI  (api/v1)           │
                    │  17 route modules · schemas       │
                    │  bulk · graph · webhooks · data    │
                    └──────────┬───────────────────────┘
                               │
                    ┌──────────▼───────────────────────┐
                    │        Service Layer              │
                    │  event · observation · memory     │
                    │  retrieval · task · log           │
                    │  webhook · graph · consolidation  │
                    │  access_tracking · import_export  │
                    └──────────┬───────────────────────┘
                               │
                    ┌──────────▼───────────────────────┐
                    │      Repository Layer             │
                    │  Generic BaseRepository[T]        │
                    │  + specialised repos              │
                    └──────────┬───────────────────────┘
                               │
                    ┌──────────▼───────────────────────┐
                    │  PostgreSQL 16+  (pgvector)       │
                    │  async via SQLAlchemy 2 + asyncpg │
                    │  tsvector full-text · JSONB        │
                    └──────────────────────────────────┘
```

---

## Data Pipeline: Event → Observation → Memory

The core abstraction follows an **event-sourced** philosophy:

1. **Events** — immutable, append-only records of _what happened_ during an
   agent run: user inputs, tool results, model outputs, system signals.

2. **Observations** — candidate facts _extracted_ from events, each tagged with
   a confidence score and source provenance.  An observation may or may not
   eventually become a memory.

3. **Memories** — the canonical knowledge store.  Each memory is identified by a
   `(user_id, memory_key)` composite and supports:
   - **Versioning**: every content change snapshots the prior version to
     `memory_versions`.
   - **Contradiction handling**: if an incoming observation conflicts with the
     current content (different hash), the memory is updated and the old
     version preserved.
   - **Deduplication**: identical content (same SHA-256 hash) is silently
     skipped — no version bump, no write.

```
  Event  ──extract──▶  Observation  ──upsert──▶  Memory
   │                        │                      │
   │ immutable              │ candidate            │ canonical + versioned
   │ append-only            │ confidence-scored     │ searchable (vector)
   │                        │                      │ auditable
```

---

## Domain Model

| Entity                 | Purpose                                       |
|------------------------|-----------------------------------------------|
| `User`                 | Tenant / owner of memories                    |
| `Project`              | Optional grouping (multi-project per user)    |
| `AgentRun`             | One invocation of an agent (session)          |
| `Event`                | Immutable record from a run                   |
| `Observation`          | Candidate fact extracted from an event         |
| `Memory`               | Canonical knowledge unit, versioned            |
| `MemoryVersion`        | Historical snapshot before an update           |
| `MemoryLink`           | Typed edge between two memories               |
| `Task`                 | Trackable work item with state machine        |
| `TaskStateTransition`  | Audit log of every state change               |
| `RetrievalLog`         | Audit of a search request                     |
| `RetrievalLogItem`     | Per-memory score breakdown in a retrieval     |
| `Artifact`             | Binary / file attachment linked to a run      |
| `APIKey`               | Hashed API key with scopes + expiry           |
| `Webhook`              | Registered webhook URL with HMAC secret       |
| `WebhookDelivery`      | Audit log for each webhook delivery attempt   |
| `MemoryAccessLog`      | Tracks every memory retrieval/view access     |

---

## Hybrid Scoring Formula

When memories are retrieved, each candidate is scored:

$$
S = w_v \cdot \text{vector\_sim} + w_r \cdot \text{recency} + w_i \cdot \text{importance} + w_a \cdot \text{authority} + w_c \cdot \text{confidence}
$$

Default weights (configurable via settings):

| Weight | Default | Signal         |
|--------|---------|----------------|
| $w_v$  | 0.45    | Vector cosine similarity |
| $w_r$  | 0.20    | Recency (exponential decay, 72 h half-life) |
| $w_i$  | 0.15    | Importance (domain-set 0–1) |
| $w_a$  | 0.10    | Authority level (normalised 0–1) |
| $w_c$  | 0.10    | Confidence (0–1) |

When no vector embedding is available for a query, vector weight is
redistributed proportionally among the remaining signals.

---

## Task State Machine

```
              ┌───────────────────────────────────┐
              ▼                                   │
         ┌─────────┐    ┌─────────────┐    ┌─────┴─────┐
    ●───▶│ pending  │───▶│ in_progress │───▶│ completed │
         └────┬────┘    └──────┬──────┘    └───────────┘
              │                │
              │                ▼
              │         ┌──────────┐
              └────────▶│ cancelled│
                        └──────┬───┘
                               │
              blocked ◀────────┘  (from in_progress)
              failed  ◀───── in_progress
```

Every transition is validated at the service layer against an allow-list and
creates an immutable `TaskStateTransition` audit record.

---

## Repository Pattern

All data access goes through **repository** classes that inherit from a generic
`BaseRepository[ModelT]`, which provides:

- `get_by_id(id) → ModelT | None`
- `list_all(**filters) → list[ModelT]`
- `create(data) → ModelT`
- `update_fields(id, **fields) → ModelT`
- `delete(id) → None`

Specialised repositories (e.g. `MemoryRepository`) add domain-specific queries
like `find_active_by_key`, `search` (hybrid vector + metadata), and
`snapshot_version`.

---

## Embedding Abstraction

```python
class BaseEmbeddingProvider(ABC):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

# Built-in implementations:
# - DummyEmbeddingProvider       (deterministic hash → N-d, for tests)
# - OpenAIEmbeddingProvider      (text-embedding-3-small)
# - CohereEmbeddingProvider      (embed-english-v3.0)
# - SentenceTransformerProvider  (all-MiniLM-L6-v2, local)
# - OllamaEmbeddingProvider      (any Ollama model, local)
```

The active provider is set at startup via `get_embedding_provider()` /
`set_embedding_provider()`.  Configuration is driven by the `EMBEDDING_PROVIDER`
env var (`"dummy"` | `"openai"` | `"cohere"` | `"sentence-transformers"` | `"ollama"`).

---

## Authentication

API-key based authentication with SHA-256 hashed storage:

- Keys are generated with an `amdb_` prefix for easy identification
- Only the SHA-256 hash is stored; raw key is shown once on creation
- Keys support comma-separated **scopes** (e.g., `read,write,admin`)
- Optional **expiry** dates with automatic enforcement
- Enabled via `REQUIRE_AUTH=true` environment variable
- Uses `X-API-Key` header for authentication

---

## Observability

### Prometheus Metrics

When `prometheus_client` is installed and `ENABLE_METRICS=true`:

| Metric | Type | Description |
|--------|------|-------------|
| `agentmemodb_request_count` | Counter | HTTP requests by method/path/status |
| `agentmemodb_request_latency_seconds` | Histogram | Request duration distribution |
| `agentmemodb_memory_upserts_total` | Counter | Memory upserts by action |
| `agentmemodb_memory_searches_total` | Counter | Searches by strategy |
| `agentmemodb_active_memories` | Gauge | Currently active memories |
| `agentmemodb_webhook_deliveries_total` | Counter | Webhook deliveries by status |

### Structured Logging

Every request gets a unique `X-Request-ID` (auto-generated or forwarded).
Structured JSON logging includes request_id, method, path, status, and latency.

---

## Webhooks

- Register webhook URLs for specific event types (or `*` for all)
- HMAC-SHA256 signed payloads for verification
- Automatic retry with configurable max attempts
- Full delivery audit trail (status codes, response bodies)

---

## Memory Graph Traversal

- **BFS Expand**: Starting from a seed memory, traverse linked memories
  up to N hops deep, with optional link-type filtering
- **Shortest Path**: Find the shortest connection between any two memories
  using bidirectional link traversal

---

## Memory Consolidation

- **Exact duplicate detection**: GROUP BY content_hash to find identical memories
- **Near-duplicate detection**: Pairwise cosine similarity above configurable threshold
- **Merge**: Archive secondary memory, inherit best governance values,
  create supersedes link, snapshot version

---

## Configuration

All settings are loaded via **pydantic-settings** from environment variables
(or `.env`):

| Variable                 | Default                          |
|--------------------------|----------------------------------|
| `DATABASE_URL`           | `postgresql+asyncpg://…`         |
| `EMBEDDING_PROVIDER`     | `dummy`                          |
| `EMBEDDING_DIMENSION`    | `1536`                           |
| `RETRIEVAL_DEFAULT_TOP_K`| `10`                             |
| `SCORE_WEIGHT_VECTOR`    | `0.45`                           |
| `OPENAI_API_KEY`         | _(optional)_                     |

See `.env.example` for the full list.

---

## Directory Layout

```
agentmemodb/
├── app/
│   ├── api/v1/           # FastAPI routes (17 modules)
│   ├── core/             # Settings, errors, auth, middleware, metrics
│   ├── db/               # Engine, session, base
│   ├── models/           # SQLAlchemy domain models (17 tables)
│   ├── repositories/     # Data-access layer
│   ├── schemas/          # Pydantic request/response
│   ├── services/         # Business logic (11 services)
│   ├── utils/            # Hashing, scoring, embeddings, extra providers
│   ├── workers/          # Background tasks
│   ├── adapters/         # Framework integrations (LangGraph)
│   ├── sdk/              # Typed async Python client
│   └── cli.py            # Click CLI management tool
├── alembic/              # Database migrations (2 revisions)
├── tests/                # Unit (12) + integration (3) tests
├── examples/             # Demo scripts & notebooks
├── docs/                 # This file and more
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── README.md
```
