# AgentMemoryDB — Detailed Technical Reference

> **SQL-native, auditable, event-sourced memory + state backend for agentic AI**
>
> Version: 0.1.0 · License: Apache 2.0 · Python 3.11+ · PostgreSQL 16+ (pgvector)

---

## Table of Contents

1. [What Is AgentMemoryDB?](#1-what-is-agentmemodb)
2. [Why It Exists — The Problem It Solves](#2-why-it-exists)
3. [Core Architecture](#3-core-architecture)
4. [The Data Pipeline: Event → Observation → Memory](#4-the-data-pipeline)
5. [Domain Models (18 Tables)](#5-domain-models)
6. [Hybrid Scoring Engine](#6-hybrid-scoring-engine)
7. [Memory Types & Lifecycle](#7-memory-types--lifecycle)
8. [Memory Versioning & Deduplication](#8-memory-versioning--deduplication)
9. [Memory Graph (Links & Traversal)](#9-memory-graph)
10. [Task State Machine](#10-task-state-machine)
11. [MCP Server (Model Context Protocol)](#11-mcp-server)
12. [WebSocket Real-Time Events](#12-websocket-real-time-events)
13. [Memory Explorer UI](#13-memory-explorer-ui)
14. [Scheduled Maintenance](#14-scheduled-maintenance)
15. [Authentication & API Keys](#15-authentication--api-keys)
16. [Row Level Security (Multi-Tenant)](#16-row-level-security)
17. [Webhooks](#17-webhooks)
18. [Data Masking (PII Compliance)](#18-data-masking)
19. [Embedding Providers](#19-embedding-providers)
20. [Full-Text Search](#20-full-text-search)
21. [Access Tracking & Popularity Boosting](#21-access-tracking)
22. [Memory Consolidation (Dedup & Merge)](#22-memory-consolidation)
23. [Import / Export](#23-import--export)
24. [Bulk Operations](#24-bulk-operations)
25. [Observability (Metrics, Logging, Tracing)](#25-observability)
26. [SDKs & Client Libraries](#26-sdks--client-libraries)
27. [CLI Tool](#27-cli-tool)
28. [LangGraph / LangChain Adapter](#28-langgraph-adapter)
29. [REST API Reference (55+ Endpoints)](#29-rest-api-reference)
30. [Configuration Reference (55+ Settings)](#30-configuration-reference)
31. [Docker & Deployment](#31-docker--deployment)
32. [Project Structure (180+ Files)](#32-project-structure)
33. [Testing](#33-testing)
34. [Pip Package (Embedded & Remote Client)](#34-pip-package)
35. [Short-Term & Long-Term Memory (MemoryManager)](#35-short-term--long-term-memory)
36. [LangChain & LangGraph Integrations](#36-langchain--langgraph-integrations)
37. [Publishing to PyPI](#37-publishing-to-pypi)

---

## 1. What Is AgentMemoryDB?

AgentMemoryDB is a **self-hosted, production-grade memory backend** purpose-built for AI agents. It gives your agents:

- **Persistent, structured memory** — not just a vector store, but typed knowledge units with versioning, governance, and audit trails
- **Hybrid retrieval** — searches combine vector similarity, recency, importance, authority, and confidence into a single composite score
- **Event sourcing** — every fact flows through an `Event → Observation → Memory` pipeline, preserving full provenance
- **Multi-protocol access** — REST API, WebSocket, Model Context Protocol (MCP), Python SDK, TypeScript SDK, CLI
- **Production features** — auth, multi-tenancy (RLS), metrics, webhooks, scheduled maintenance, Docker-native

It runs as a **single FastAPI service** backed by **PostgreSQL + pgvector**, deployable with one `docker compose up` command.

---

## 2. Why It Exists

Most agentic frameworks treat memory as an afterthought:

| Problem | How Most Frameworks Handle It | How AgentMemoryDB Handles It |
|---------|-------------------------------|------------------------------|
| Memory storage | JSON blob or vector-only store | PostgreSQL with JSONB + pgvector + full-text |
| Audit trail | Fire-and-forget writes | Every mutation versioned; every retrieval logged |
| Search quality | Vector similarity only | 5-signal hybrid scoring (vector + recency + importance + authority + confidence) |
| Contradiction handling | Overwrite or ignore | Detect via content hash, create version, update |
| Multi-tenancy | Application-level filtering | PostgreSQL Row Level Security |
| Real-time updates | Polling | WebSocket pub/sub with channel subscriptions |
| AI agent interop | Custom integrations | Standard Model Context Protocol (MCP) |
| Maintenance | Manual cleanup | 5 automated scheduled jobs |
| Observability | DIY logging | Prometheus metrics + structured logging + request tracing |

---

## 3. Core Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                    Clients / Agents                               │
│  Python SDK · TypeScript SDK · CLI · REST · MCP · WebSocket       │
└────────────────────────────┬──────────────────────────────────────┘
                             │
┌────────────────────────────▼──────────────────────────────────────┐
│                     Middleware Stack                               │
│  CORS · Request ID · Timing · API-Key Auth · Prometheus Counter   │
└────────────────────────────┬──────────────────────────────────────┘
                             │
┌────────────────────────────▼──────────────────────────────────────┐
│                   FastAPI Application                              │
│                                                                   │
│  REST Routes (20 modules)        MCP Server (JSON-RPC 2.0)       │
│  ├── /api/v1/health              ├── tools/list                  │
│  ├── /api/v1/users               ├── tools/call                  │
│  ├── /api/v1/projects            ├── resources/list              │
│  ├── /api/v1/runs                └── resources/read              │
│  ├── /api/v1/events                                              │
│  ├── /api/v1/observations        WebSocket (/ws)                 │
│  ├── /api/v1/memories            ├── Channel subscriptions       │
│  ├── /api/v1/memory-links        ├── subscribe/unsubscribe       │
│  ├── /api/v1/tasks               └── Real-time event broadcast   │
│  ├── /api/v1/retrieval-logs                                      │
│  ├── /api/v1/artifacts           Explorer UI (/explorer)         │
│  ├── /api/v1/api-keys            ├── React + Vite + Tailwind     │
│  ├── /api/v1/webhooks            ├── D3.js graph visualization   │
│  ├── /api/v1/bulk                ├── Search + detail + scores    │
│  ├── /api/v1/graph               └── Live event feed             │
│  ├── /api/v1/consolidation                                       │
│  ├── /api/v1/data                Scheduler (background)          │
│  ├── /api/v1/scheduler           ├── consolidate_duplicates      │
│  └── /api/v1/mcp                 ├── archive_stale               │
│                                  ├── recompute_recency           │
│                                  ├── cleanup_expired             │
│                                  └── prune_access_logs           │
└────────────────────────────┬──────────────────────────────────────┘
                             │
┌────────────────────────────▼──────────────────────────────────────┐
│                    Service Layer (11 services)                    │
│  MemoryService · RetrievalService · EventService                 │
│  ObservationService · TaskService · GraphService                 │
│  ConsolidationService · WebhookService · ImportExportService     │
│  AccessTrackingService · RetrievalLogService                     │
└────────────────────────────┬──────────────────────────────────────┘
                             │
┌────────────────────────────▼──────────────────────────────────────┐
│                   Repository Layer (10 repos)                    │
│  BaseRepository[T] → get_by_id · list_all · create · update     │
│  + MemoryRepository (hybrid search, version snapshots)           │
│  + EventRepository · ObservationRepository · TaskRepository      │
│  + ProjectRepository · RunRepository · UserRepository            │
│  + ArtifactRepository · RetrievalLogRepository                   │
└────────────────────────────┬──────────────────────────────────────┘
                             │
┌────────────────────────────▼──────────────────────────────────────┐
│               PostgreSQL 16+ with pgvector                       │
│  17 tables · JSONB payloads · Vector(1536) embeddings            │
│  IVFFlat index · tsvector full-text · GIN indexes                │
│  Row Level Security (optional)                                   │
└───────────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | Role | Files |
|-------|------|-------|
| **Routes** (api/v1/) | HTTP/WS/MCP request handling, validation, response shaping | 20 modules |
| **Schemas** (schemas/) | Pydantic v2 request/response models, validation rules | 12 modules |
| **Services** (services/) | Business logic, orchestration, domain rules | 11 modules |
| **Repositories** (repositories/) | Data access, SQL queries, async SQLAlchemy 2 | 10 modules |
| **Models** (models/) | SQLAlchemy ORM table definitions | 16 models |
| **Utils** | Embedding providers, scoring, hashing, extra providers | 4 modules |
| **Core** | Settings, auth, middleware, errors, metrics | 6 modules |

---

## 4. The Data Pipeline

The core design follows **event sourcing** — knowledge doesn't appear out of thin air, it flows through a traceable pipeline:

```
  Event (immutable, append-only)
    │
    ├── extract ──▶  Observation (candidate fact, confidence-scored)
    │                      │
    │                      ├── upsert ──▶  Memory (canonical, versioned, searchable)
    │                      │                  │
    │                      │                  ├── content_hash dedup → skip if identical
    │                      │                  ├── contradiction → new version
    │                      │                  └── new key → create
```

### Step 1: Events

An **Event** is an immutable record of something that happened during an agent run. It could be a user message, a tool result, a model response, or a system signal.

```json
{
  "run_id": "run-uuid",
  "event_type": "user_message",
  "content": "I prefer Python for backend work",
  "metadata": {"source": "chat"}
}
```

### Step 2: Observations

An **Observation** is a candidate fact extracted from an event. It's tagged with a confidence score and source provenance. Not every observation becomes a memory.

```json
{
  "event_id": "event-uuid",
  "content": "User prefers Python for backend development",
  "observation_type": "preference",
  "confidence": 0.85,
  "source": "llm_extraction"
}
```

You can auto-extract observations from events via `POST /observations/extract-from-event`.

### Step 3: Memories

A **Memory** is the canonical knowledge unit. It's identified by `(user_id, memory_key)` and supports versioning, contradiction detection, and deduplication.

```json
{
  "user_id": "user-uuid",
  "memory_key": "pref:backend_language",
  "memory_type": "semantic",
  "content": "User prefers Python for backend development",
  "importance_score": 0.8,
  "confidence": 0.85
}
```

---

## 5. Domain Models

AgentMemoryDB uses **19 database tables** (18 server + 1 embedded):

| Table | Purpose | Key Fields |
|-------|---------|------------|
| **users** | Tenant / owner identity | `id`, `name`, `metadata` |
| **projects** | Optional grouping of runs | `id`, `user_id`, `name` |
| **agent_runs** | One invocation of an agent | `id`, `user_id`, `project_id`, `status`, `started_at`, `completed_at` |
| **events** | Immutable records from a run | `id`, `run_id`, `event_type`, `content`, `metadata`, `occurred_at` |
| **observations** | Candidate facts from events | `id`, `event_id`, `content`, `observation_type`, `confidence`, `source` |
| **memories** | Canonical knowledge units | `id`, `user_id`, `memory_key`, `memory_type`, `content`, `scope`, `status`, `version`, `embedding` (Vector), `content_hash`, `importance_score`, `confidence`, `authority_level`, `payload` (JSONB) |
| **memory_versions** | Historical snapshots | `id`, `memory_id`, `version`, `content`, `payload`, `created_at` |
| **memory_links** | Typed edges between memories | `id`, `source_memory_id`, `target_memory_id`, `link_type`, `description`, `weight` |
| **tasks** | Trackable work items | `id`, `user_id`, `title`, `description`, `state`, `priority`, `assigned_to` |
| **task_state_transitions** | State change audit trail | `id`, `task_id`, `from_state`, `to_state`, `reason`, `triggered_by` |
| **retrieval_logs** | Search audit headers | `id`, `user_id`, `query_text`, `strategy`, `top_k`, `duration_ms` |
| **retrieval_log_items** | Per-memory score breakdowns | `id`, `log_id`, `memory_id`, `rank`, `vector_score`, `recency_score`, …, `final_score` |
| **artifacts** | File/binary attachment metadata | `id`, `run_id`, `name`, `content_type`, `size_bytes`, `storage_path` |
| **api_keys** | Hashed API keys with scopes | `id`, `key_hash`, `prefix`, `scopes`, `expires_at` |
| **webhooks** | Registered callback URLs | `id`, `url`, `secret`, `event_types`, `active` |
| **webhook_deliveries** | Delivery audit log | `id`, `webhook_id`, `status_code`, `response_body`, `attempt` |
| **memory_access_logs** | Access pattern tracking | `id`, `memory_id`, `user_id`, `access_type`, `accessed_at` |
| **masking_logs** | PII masking audit trail | `id`, `entity_type`, `entity_id`, `field_name`, `patterns_detected` (JSONB), `detection_count`, `original_content_hash` |
| **thread_messages** *(embedded)* | Short-term conversation buffer | `id`, `thread_id`, `role`, `content`, `metadata` (JSON), `seq`, `created_at` |

---

## 6. Hybrid Scoring Engine

Every memory retrieval computes a **5-signal weighted composite score**:

$$S = w_v \cdot \text{vector} + w_r \cdot \text{recency} + w_i \cdot \text{importance} + w_a \cdot \text{authority} + w_c \cdot \text{confidence}$$

| Signal | Default Weight | Source | How It Works |
|--------|----------------|--------|--------------|
| **Vector similarity** | 0.45 | pgvector cosine distance | Embedding of query vs. memory content. Uses IVFFlat index. |
| **Recency** | 0.20 | `updated_at` field | Exponential decay with 72-hour half-life: `score = 0.5^(hours_since_update / 72)` |
| **Importance** | 0.15 | Domain-supplied 0–1 | Set on upsert. Optionally boosted by access frequency. |
| **Authority** | 0.10 | `authority_level` (0–10) | Normalized to 0–1. Higher = more trusted source. |
| **Confidence** | 0.10 | Observation confidence | How certain the system is about this fact. |

### Special Behaviors

- **No embedding available**: When the query has no vector, the 0.45 vector weight is **redistributed proportionally** among the other 4 signals
- **Access frequency boosting**: When enabled, frequently accessed memories get an importance boost: `importance += access_count × boost_factor` (capped at 1.0)
- **All weights configurable** via `SCORE_WEIGHT_*` environment variables
- **Weights validated** to sum to 1.0 at startup

---

## 7. Memory Types & Lifecycle

### Memory Types

| Type | Purpose | Example |
|------|---------|---------|
| **semantic** | Factual knowledge, preferences, definitions | "User prefers Python" |
| **episodic** | Specific events or experiences | "User had a frustrating debug session on Jan 5" |
| **procedural** | How-to knowledge, workflows, instructions | "To deploy: run make deploy, then check /health" |
| **working** | Short-term, session-scoped context | "User is currently working on the payments module" |

### Memory Scopes

| Scope | Description |
|-------|-------------|
| `user` | Personal to the user |
| `project` | Shared across a project |
| `global` | Available to all users |
| `session` | Scoped to an agent run |

### Memory Statuses

| Status | Meaning |
|--------|---------|
| `active` | Live, searchable, retrievable |
| `archived` | Preserved but excluded from default search |
| `retracted` | Marked as incorrect, excluded from search |

---

## 8. Memory Versioning & Deduplication

### Versioning

Every time a memory's content changes, the **previous content is snapshotted** to `memory_versions` before the update is applied. This creates a complete audit trail:

```
Memory "pref:language" v1: "User likes JavaScript"    → saved to memory_versions
Memory "pref:language" v2: "User likes TypeScript"    → saved to memory_versions  
Memory "pref:language" v3: "User prefers Python"      → current
```

You can retrieve the full version history via `GET /api/v1/memories/{id}/versions`.

### Deduplication

Each memory stores a `content_hash` (SHA-256). On upsert:

1. **Identical content** (same hash) → **skip silently** — no write, no version bump
2. **Different content** (different hash) → **create version snapshot**, update content, bump version
3. **New key** → **create new memory** at version 1

This ensures no unnecessary writes while preserving a full history of meaningful changes.

---

## 9. Memory Graph

Memories can be connected via **typed, weighted edges** called Memory Links.

### Link Types

Links have a `link_type` (string) that describes the relationship:

- `related_to` — general association
- `depends_on` — prerequisite
- `contradicts` — conflicting information
- `supersedes` — newer version of an older memory
- `elaborates` — provides more detail
- Any custom string you define

### Graph Operations

| Operation | Endpoint | Description |
|-----------|----------|-------------|
| **Create link** | `POST /api/v1/memory-links` | Create a directed edge between two memories |
| **BFS Expand** | `GET /api/v1/graph/expand/{id}` | Starting from a seed memory, traverse N hops outward. Returns all reachable nodes with depth, link type, and direction. |
| **Shortest Path** | `POST /api/v1/graph/shortest-path` | Find the shortest connection between any two memories using bidirectional traversal. |

### Expand Example

```bash
GET /api/v1/graph/expand/memory-uuid?max_hops=2&max_nodes=50
```

Returns:
```json
[
  {"memory_id": "...", "memory_key": "pref:lang", "depth": 0, "link_type": null},
  {"memory_id": "...", "memory_key": "skill:python", "depth": 1, "link_type": "related_to"},
  {"memory_id": "...", "memory_key": "project:backend", "depth": 2, "link_type": "depends_on"}
]
```

The Explorer UI renders this as an interactive D3.js force-directed graph with drag, zoom, and click-to-explore.

---

## 10. Task State Machine

AgentMemoryDB includes a built-in task tracking system with **validated state transitions**:

```
              ┌──────────────────────────────────────┐
              ▼                                      │
         ┌──────────┐      ┌──────────────┐     ┌───┴───────┐
    ●───▶│ pending   │─────▶│ in_progress  │────▶│ completed │
         └─────┬────┘      └──────┬───────┘     └───────────┘
               │                  │
               │                  ├────▶ waiting_review ──▶ completed / in_progress
               │                  ├────▶ failed
               │                  └────▶ cancelled
               │
               └──────────────────────▶ cancelled
```

### Allowed Transitions

| From | To |
|------|----|
| `pending` | `in_progress`, `cancelled` |
| `in_progress` | `waiting_review`, `completed`, `failed`, `cancelled` |
| `waiting_review` | `in_progress`, `completed`, `failed`, `cancelled` |
| `failed` | `pending` (retry) |
| `cancelled` | `pending` (reopen) |

Every transition creates an immutable **TaskStateTransition** audit record with `reason` and `triggered_by`.

---

## 11. MCP Server (Model Context Protocol)

AgentMemoryDB includes a built-in **MCP server** that lets AI agents (Claude, Cursor, custom agents) interact with memory through the standard Model Context Protocol (JSON-RPC 2.0).

### Endpoint

```
POST /api/v1/mcp/message
```

### 7 MCP Tools

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| **store_memory** | Create or update a memory | `user_id`, `memory_key`, `content`, `memory_type`, `importance_score` |
| **recall_memories** | Semantic search for relevant memories | `user_id`, `query`, `top_k`, `memory_types` |
| **get_memory** | Retrieve a specific memory by ID | `memory_id` |
| **link_memories** | Create a relationship between memories | `source_id`, `target_id`, `link_type`, `description` |
| **record_event** | Record an event from an agent run | `run_id`, `event_type`, `content` |
| **explore_graph** | Traverse memory graph from a seed | `memory_id`, `max_hops` |
| **consolidate_memories** | Trigger dedup + merge for a user | `user_id` |

### MCP Resources

| Resource | URI | Description |
|----------|-----|-------------|
| **Schema** | `memory://schema` | Full database schema info |
| **Stats** | `memory://stats` | Current memory statistics |

### Transports

- **HTTP + SSE**: For Cursor, Claude Desktop, and web-based agents
- **stdio**: For local agents running in the same process

### Example MCP Call

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "recall_memories",
    "arguments": {
      "user_id": "abc-123",
      "query": "What programming language does the user prefer?",
      "top_k": 5
    }
  },
  "id": 1
}
```

---

## 12. WebSocket Real-Time Events

Subscribe to live memory changes via WebSocket:

### Connection

```
ws://localhost:8100/ws?channels=user:abc-123,project:def-456
```

### Channel Patterns

| Pattern | Receives |
|---------|----------|
| `global` | All events system-wide |
| `user:{user_id}` | Events for a specific user |
| `project:{project_id}` | Events for a project |
| `memory:{memory_id}` | Changes to a specific memory |

### Event Types

| Event | Trigger |
|-------|---------|
| `memory.created` | New memory stored |
| `memory.updated` | Memory content changed |
| `memory.archived` | Memory status → archived |
| `memory.retracted` | Memory status → retracted |
| `memory.linked` | Link created between memories |
| `memory.consolidated` | Memories merged |
| `event.recorded` | New event recorded |

### In-Session Commands

Once connected, clients can send JSON commands:

```json
{"action": "subscribe", "channel": "user:new-user-id"}
{"action": "unsubscribe", "channel": "user:old-user-id"}
{"action": "ping"}
{"action": "status"}
```

### Connection Management

- Auto-reconnect on disconnect (client-side)
- Dead connection cleanup on broadcast
- Multiple simultaneous channel subscriptions per connection
- Global broadcast reaches all connected clients

---

## 13. Memory Explorer UI

A built-in **React + Vite + Tailwind CSS** web dashboard served at `/explorer`:

### Features

| Page | Description |
|------|-------------|
| **Dashboard** | Health status, version info, database/embedding provider, scheduler controls |
| **Explorer** | Full memory search with type filters, result list, detailed view with score bars, version history, linked memories |
| **Graph** | Interactive D3.js force-directed graph with zoom/pan/drag, configurable hops, color-coded nodes by type, hover tooltips |
| **Events** | Real-time WebSocket event feed with channel subscriptions, auto-reconnect, event history |
| **Settings** | API configuration, connection management |

### Stack

- **React 18** with TypeScript
- **Vite 6** for build/dev server
- **Tailwind CSS 3** with GitHub-dark custom theme
- **D3.js v7** for force-directed graph visualization
- **React Router v6** for SPA navigation
- **Lucide React** for icons

### Access

```
http://localhost:8100/explorer      # Production (served by FastAPI)
http://localhost:5173/explorer      # Development (Vite dev server with API proxy)
```

---

## 14. Scheduled Maintenance

AgentMemoryDB runs **5 automated maintenance jobs** in the background:

| Job | Default Interval | Description |
|-----|-----------------|-------------|
| **consolidate_duplicates** | 60 min | Find exact duplicate memories (same `content_hash`) and merge them — archive the secondary, preserve the primary, create `supersedes` link |
| **archive_stale** | 120 min | Archive active memories not updated in N days (default: 90). Low-importance memories are archived first. |
| **recompute_recency** | 30 min | Refresh recency scores for all active memories based on current `updated_at` timestamps |
| **cleanup_expired** | 60 min | Retract memories that have passed their `expires_at` timestamp |
| **prune_access_logs** | 24 hours | Delete access log entries older than N days (default: 90) |

### Controls

- Each job is individually **toggleable** via `SCHEDULER_ENABLE_*` env vars
- Each job's **interval** is configurable via `SCHEDULER_*_INTERVAL` env vars
- Jobs can be **triggered manually** via `POST /api/v1/scheduler/jobs/{name}/run`
- **Status** of all jobs available via `GET /api/v1/scheduler/status`
- Jobs track `run_count`, `last_run`, and `errors`

---

## 15. Authentication & API Keys

### How It Works

1. Generate a key via `POST /api/v1/api-keys` — returns the raw key **once**
2. System stores only the **SHA-256 hash** (raw key is never persisted)
3. Keys have an `amdb_` prefix for easy identification
4. Clients send keys via `X-API-Key` header
5. System hashes the incoming key and compares with stored hash

### Key Features

| Feature | Description |
|---------|-------------|
| **Scopes** | Comma-separated (e.g., `read,write,admin`) |
| **Expiry** | Optional `expires_at` timestamp with auto-enforcement |
| **Revocation** | `DELETE /api/v1/api-keys/{id}` immediately invalidates |
| **Prefix matching** | Keys identified by their first 8 chars for audit logging |

### Enable Auth

```bash
REQUIRE_AUTH=true  # in .env
```

---

## 16. Row Level Security

PostgreSQL Row Level Security for database-level tenant isolation:

### Three Roles

| Role | Permissions |
|------|------------|
| `agentmemodb_anon` | Read-only access to own data |
| `agentmemodb_user` | Full CRUD on own data |
| `agentmemodb_admin` | Unrestricted access to all data |

### How It Works

1. Run the RLS migration: `alembic upgrade 004_add_rls`
2. Set `ENABLE_RLS=true` in environment
3. Before each query, the service layer calls `set_tenant_context(user_id)` which sets a PostgreSQL session variable
4. RLS policies on every table filter rows to match the current tenant
5. Even raw SQL or a compromised ORM layer **cannot access other tenants' data**

This provides **defense in depth** — even if the application layer has a bug, the database itself enforces isolation.

---

## 17. Webhooks

### How It Works

1. Register a webhook: `POST /api/v1/webhooks` with URL, secret, and event types
2. When a matching event occurs, AgentMemoryDB sends an HTTP POST to your URL
3. Payload is **HMAC-SHA256 signed** using your secret for verification
4. Failed deliveries are **retried** with configurable max attempts
5. Every delivery attempt is **audited** (status code, response body, timing)

### Supported Event Types

- `memory.created`, `memory.updated`, `memory.archived`, `memory.retracted`
- `*` — subscribe to all events

### Webhook Registration

```json
{
  "url": "https://your-app.com/webhooks/memory",
  "secret": "your-hmac-secret",
  "event_types": ["memory.created", "memory.updated"],
  "active": true
}
```

---

## 18. Data Masking (PII Compliance)

Write-time PII masking with full-replacement tokens. When enabled, PII is detected and replaced **before** data reaches the database — the original value is never persisted.

### How It Works

```
  Incoming content ("Email josh@co.com, SSN 123-45-6789")
       │
       ▼
  PII Masking Engine (regex-based, configurable patterns)
       │
       ▼
  Masked content ("Email [EMAIL], SSN [SSN]")
       │
       ▼
  PostgreSQL (PII never stored)
       +
  masking_logs audit table (pattern names + counts, no raw PII)
```

### Built-in PII Patterns

| Pattern | Example Input | Replacement | Description |
|---------|--------------|-------------|-------------|
| **email** | `josh@company.com` | `[EMAIL]` | RFC-compliant email addresses |
| **phone** | `+1-555-123-4567` | `[PHONE]` | US/international formats |
| **ssn** | `123-45-6789` | `[SSN]` | US Social Security Numbers |
| **credit_card** | `4111-1111-1111-1111` | `[CREDIT_CARD]` | Visa, MC, Amex, Discover |
| **ip_address** | `192.168.1.100` | `[IP_ADDRESS]` | IPv4 addresses |
| **us_passport** | `A12345678` | `[PASSPORT]` | US passport numbers |
| **date_of_birth** | `DOB: 01/15/1990` | `[DOB]` | Dates preceded by DOB keywords |

### Pipeline Coverage

Masking is applied at **write-time** across the entire data pipeline:

| Data Flow | Where Masked | What’s Masked |
|-----------|-------------|---------------|
| **Events** | `EventService.create_event()` | `content` field |
| **Observations** | `ObservationService.create_observation()` | `content` field |
| **Observations** (extracted) | `ObservationService.extract_from_event()` | `content` field |
| **Memories** | `MemoryService.upsert()` | `content` field (before content_hash) |

### Custom Patterns

Define custom regex patterns via the `MASKING_CUSTOM_PATTERNS` env var (JSON array):

```bash
MASKING_CUSTOM_PATTERNS='[{"name": "employee_id", "regex": "EMP-\\d{6}", "token": "[EMPLOYEE_ID]"}]'
```

### Audit Trail

Every masking action creates an immutable `masking_logs` entry:
- **Entity reference** — which memory/event/observation was masked
- **Pattern names** — which PII types were detected (`["email", "phone"]`)
- **Detection count** — how many PII instances were found
- **Content hash** — SHA-256 of original text (for forensic correlation, not PII recovery)
- **No raw PII stored** — the log never contains the original masked text

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/masking/config` | Current masking configuration |
| POST | `/api/v1/masking/test` | Dry-run masking on arbitrary text |
| GET | `/api/v1/masking/logs` | Query masking audit logs |
| GET | `/api/v1/masking/stats` | Aggregate masking statistics |

### Configuration

```bash
ENABLE_DATA_MASKING=true                    # Master switch (default: false)
MASKING_PATTERNS=email,phone,ssn,credit_card,ip_address  # Which patterns to activate
MASKING_LOG_DETECTIONS=true                 # Write audit log entries (default: true)
MASKING_CUSTOM_PATTERNS=null                # Optional JSON array of custom patterns
```

---

## 19. Embedding Providers

AgentMemoryDB supports **5 embedding providers**:

| Provider | Config Value | Model | Runs Where |
|----------|-------------|-------|------------|
| **Dummy** | `dummy` | Deterministic hash → N-d vector | Local (for tests) |
| **OpenAI** | `openai` | `text-embedding-3-small` (configurable) | API call |
| **Cohere** | `cohere` | `embed-english-v3.0` | API call |
| **Sentence Transformers** | `sentence-transformers` | `all-MiniLM-L6-v2` (configurable) | Local GPU/CPU |
| **Ollama** | `ollama` | `nomic-embed-text` (configurable) | Local server |

### Configuration

```bash
EMBEDDING_PROVIDER=openai         # or dummy, cohere, sentence-transformers, ollama
EMBEDDING_DIMENSION=1536          # must match model output dimension
OPENAI_API_KEY=sk-...             # required for openai
COHERE_API_KEY=...                # required for cohere
OLLAMA_BASE_URL=http://localhost:11434  # for ollama
OLLAMA_MODEL=nomic-embed-text     # for ollama
```

### Provider Abstraction

All providers implement the same interface:

```python
class BaseEmbeddingProvider(ABC):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    @property
    def dimension(self) -> int: ...
```

---

## 20. Full-Text Search

In addition to vector similarity, AgentMemoryDB supports **PostgreSQL tsvector full-text search**:

- Memories are indexed with a `tsvector` column for keyword matching
- Full-text results are combined with vector results in the hybrid scoring formula
- Configurable weight: `FULLTEXT_WEIGHT=0.1`
- Enable/disable: `ENABLE_FULLTEXT_SEARCH=true`
- Uses PostgreSQL's GIN index for fast text matching

This is useful when vector search alone misses exact keyword matches (e.g., product names, acronyms, error codes).

---

## 21. Access Tracking

AgentMemoryDB tracks every memory retrieval and uses access frequency to boost importance:

### How It Works

1. Every time a memory appears in search results, an access log entry is created
2. The system counts accesses within a configurable window (default: 7 days)
3. Frequently accessed memories get an importance boost: `importance += count × factor`
4. This creates a natural "popularity" signal — memories that agents find useful become more prominent

### Configuration

```bash
ENABLE_ACCESS_TRACKING=true
ACCESS_BOOST_FACTOR=0.05          # importance boost per access
ACCESS_BOOST_WINDOW_HOURS=168     # 7-day window
```

---

## 22. Memory Consolidation

Automated deduplication and merge of memories:

### Detection Methods

| Method | How |
|--------|-----|
| **Exact duplicates** | `GROUP BY content_hash` — same SHA-256 hash |
| **Near duplicates** | Pairwise cosine similarity above configurable threshold |

### Merge Process

1. Primary memory is kept as `active`
2. Secondary memory is set to `archived`
3. Best governance values are inherited (higher importance, authority, confidence)
4. A `supersedes` link is created from primary → secondary
5. Version snapshot is created before the merge

### Triggers

- **Automatic**: via scheduled `consolidate_duplicates` job
- **Manual**: `POST /api/v1/consolidation/auto` (all users) or `POST /api/v1/consolidation/merge` (specific pair)

---

## 23. Import / Export

### Export

```bash
GET /api/v1/data/export?user_id=abc-123
```

Returns a JSON array of all memories for a user, suitable for backup or migration.

### Import

```bash
POST /api/v1/data/import
Content-Type: application/json

[
  {"memory_key": "pref:lang", "content": "User likes Python", ...},
  {"memory_key": "pref:editor", "content": "Uses VS Code", ...}
]
```

Memories are upserted — existing keys are updated, new keys are created.

---

## 24. Bulk Operations

### Batch Upsert

```bash
POST /api/v1/bulk/upsert
```

Upsert up to **100 memories** in a single request. Returns per-item success/failure status.

### Batch Search

```bash
POST /api/v1/bulk/search
```

Run up to **20 queries** in a single request. Returns results for each query.

---

## 25. Observability

### Prometheus Metrics

When `ENABLE_METRICS=true` and `prometheus_client` is installed:

| Metric | Type | Description |
|--------|------|-------------|
| `agentmemodb_request_count` | Counter | HTTP requests by method/path/status |
| `agentmemodb_request_latency_seconds` | Histogram | Request duration distribution |
| `agentmemodb_memory_upserts_total` | Counter | Memory upserts by action (created/updated/skipped) |
| `agentmemodb_memory_searches_total` | Counter | Searches by strategy |
| `agentmemodb_active_memories` | Gauge | Currently active memory count |
| `agentmemodb_webhook_deliveries_total` | Counter | Webhook deliveries by status |

Exposed at `GET /metrics` (root path, not under `/api/v1`).

### Structured Logging

- Every request gets a unique `X-Request-ID` (auto-generated or forwarded from client)
- JSON-structured log output with `request_id`, `method`, `path`, `status`, `latency`
- Process time exposed via `X-Process-Time` response header

### Request Tracing

- `X-Request-ID` header propagated through all service/repository calls
- Retrieval log entries link search queries to returned results with full score breakdowns

---

## 26. SDKs & Client Libraries

### Python SDK

```python
from app.sdk import AgentMemoryDBClient

async with AgentMemoryDBClient(
    base_url="http://localhost:8100",
    api_key="amdb_...",
) as client:
    memory = await client.upsert_memory(
        user_id=user_id,
        memory_key="pref:lang",
        memory_type="semantic",
        content="User prefers Python",
    )
    results = await client.search_memories(user_id=user_id, query_text="language?")
    graph = await client.expand_graph(memory["id"], max_hops=2)
    batch = await client.bulk_upsert([item1, item2, item3])
```

### TypeScript SDK

```typescript
import { AgentMemoryDB } from '@agentmemorydb/sdk';

const db = new AgentMemoryDB({
  baseUrl: 'http://localhost:8100',
  apiKey: 'amdb_...',
});

// CRUD
const memory = await db.memories.upsert({ userId, memoryKey: 'pref', content: '...' });
const results = await db.memories.search({ userId, queryText: 'What...?' });

// Real-time
const ws = db.realtime(['user:abc-123']);
ws.on('memory.created', (data) => console.log(data));
```

---

## 27. CLI Tool

```bash
agentmemodb health                           # Health check
agentmemodb stats                            # Memory statistics
agentmemodb export --user-id UUID -o out.json   # Export to JSON
agentmemodb import data.json                 # Import from JSON
agentmemodb archive-stale --days 90          # Archive old memories
agentmemodb consolidate                      # Run dedup + merge
agentmemodb recompute-recency                # Refresh recency scores
```

---

## 28. LangGraph Adapter

A lightweight adapter for LangGraph / LangChain integration:

```python
from app.adapters.langgraph_store import AgentMemoryDBStore

store = AgentMemoryDBStore(base_url="http://localhost:8100/api/v1")

await store.put(user_id, "pref:color", "User likes blue.")
results = await store.search(user_id, "What colour?", top_k=3)
```

---

## 29. REST API Reference

All endpoints under `/api/v1`:

### Health & System

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Readiness check |
| GET | `/health/deep` | Deep health (DB + pgvector + count) |
| GET | `/version` | Version + feature flags |
| GET | `/metrics` | Prometheus metrics (root path) |

### Users, Projects, Runs

| Method | Path | Description |
|--------|------|-------------|
| POST | `/users` | Create user |
| GET | `/users/{id}` | Get user |
| POST | `/projects` | Create project |
| GET | `/projects` | List projects |
| POST | `/runs` | Create agent run |
| PATCH | `/runs/{id}/complete` | Mark run completed |

### Events & Observations

| Method | Path | Description |
|--------|------|-------------|
| POST | `/events` | Record event |
| GET | `/events` | List events |
| POST | `/observations` | Record observation |
| POST | `/observations/extract-from-event` | Auto-extract from event |
| GET | `/observations` | List observations |

### Memories (Core)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/memories/upsert` | Create or update memory |
| POST | `/memories/search` | Hybrid search |
| GET | `/memories/{id}` | Get by ID |
| GET | `/memories` | List with filters |
| PATCH | `/memories/{id}/status` | Update status |
| GET | `/memories/{id}/versions` | Version history |
| GET | `/memories/{id}/links` | Related memories |
| POST | `/memory-links` | Create link |

### Bulk Operations

| Method | Path | Description |
|--------|------|-------------|
| POST | `/bulk/upsert` | Batch upsert (≤100) |
| POST | `/bulk/search` | Batch search (≤20) |

### Graph

| Method | Path | Description |
|--------|------|-------------|
| GET | `/graph/expand/{id}` | BFS traversal |
| POST | `/graph/shortest-path` | Shortest path |

### Consolidation

| Method | Path | Description |
|--------|------|-------------|
| GET | `/consolidation/duplicates` | Find duplicates |
| POST | `/consolidation/merge` | Merge two memories |
| POST | `/consolidation/auto` | Auto-consolidate |

### Data I/O

| Method | Path | Description |
|--------|------|-------------|
| GET | `/data/export` | Export as JSON |
| POST | `/data/import` | Import from JSON |

### Tasks

| Method | Path | Description |
|--------|------|-------------|
| POST | `/tasks` | Create task |
| GET | `/tasks/{id}` | Get task |
| GET | `/tasks` | List tasks |
| PATCH | `/tasks/{id}/transition` | State transition |

### Auth & Webhooks

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api-keys` | Create API key |
| DELETE | `/api-keys/{id}` | Revoke key |
| POST | `/webhooks` | Register webhook |
| GET | `/webhooks` | List webhooks |
| DELETE | `/webhooks/{id}` | Delete webhook |

### Audit

| Method | Path | Description |
|--------|------|-------------|
| POST | `/retrieval-logs` | Create retrieval audit |
| POST | `/artifacts` | Upload artifact metadata |
| GET | `/artifacts/{id}` | Get artifact |

### MCP & Scheduler

| Method | Path | Description |
|--------|------|-------------|
| POST | `/mcp/message` | MCP JSON-RPC 2.0 |
| GET | `/mcp/tools` | List MCP tools |
| GET | `/scheduler/status` | Scheduler status |
| POST | `/scheduler/jobs/{name}/run` | Trigger job |

### Data Masking

| Method | Path | Description |
|--------|------|-------------|
| GET | `/masking/config` | Current masking config |
| POST | `/masking/test` | Dry-run PII detection |
| GET | `/masking/logs` | Query masking audit logs |
| GET | `/masking/stats` | Aggregate masking stats |

### WebSocket

| Protocol | Path | Description |
|----------|------|-------------|
| WS | `/ws` | Real-time events |

---

## 30. Configuration Reference

All settings via environment variables or `.env`:

### Application

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `AgentMemoryDB` | Application name |
| `ENVIRONMENT` | `development` | Environment name |
| `LOG_LEVEL` | `INFO` | Python log level |
| `ENABLE_DOCS` | `true` | Enable Swagger/ReDoc |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Async Postgres URL |
| `DATABASE_ECHO` | `false` | Log SQL statements |

### Embeddings

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_PROVIDER` | `dummy` | `dummy`, `openai`, `cohere`, `sentence-transformers`, `ollama` |
| `EMBEDDING_DIMENSION` | `1536` | Vector dimension |
| `VECTOR_INDEX_LISTS` | `100` | IVFFlat lists parameter |
| `OPENAI_API_KEY` | — | Required for openai |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI model name |
| `COHERE_API_KEY` | — | Required for cohere |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `OLLAMA_MODEL` | `nomic-embed-text` | Ollama model |

### Retrieval & Scoring

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_TOP_K` | `10` | Default search result limit |
| `SCORE_WEIGHT_VECTOR` | `0.45` | Vector similarity weight |
| `SCORE_WEIGHT_RECENCY` | `0.20` | Recency weight |
| `SCORE_WEIGHT_IMPORTANCE` | `0.15` | Importance weight |
| `SCORE_WEIGHT_AUTHORITY` | `0.10` | Authority weight |
| `SCORE_WEIGHT_CONFIDENCE` | `0.10` | Confidence weight |
| `ENABLE_FULLTEXT_SEARCH` | `true` | Enable tsvector search |
| `FULLTEXT_WEIGHT` | `0.1` | Full-text weight in hybrid |

### Auth & Security

| Variable | Default | Description |
|----------|---------|-------------|
| `REQUIRE_AUTH` | `false` | Enforce API key auth |
| `ENABLE_RLS` | `false` | Enable Row Level Security |

### Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_WEBHOOKS` | `true` | Enable webhook delivery |
| `ENABLE_METRICS` | `true` | Enable Prometheus metrics |
| `ENABLE_ACCESS_TRACKING` | `true` | Track access patterns |
| `ENABLE_WEBSOCKET` | `true` | Enable WebSocket endpoint |
| `ENABLE_MCP` | `true` | Enable MCP server |
| `ENABLE_EXPLORER` | `true` | Enable Explorer UI |
| `ENABLE_SCHEDULER` | `true` | Enable scheduled jobs |

### Data Masking

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_DATA_MASKING` | `false` | Master switch for PII masking |
| `MASKING_PATTERNS` | `email,phone,ssn,credit_card,ip_address` | Comma-separated built-in patterns |
| `MASKING_LOG_DETECTIONS` | `true` | Write audit log for masking actions |
| `MASKING_CUSTOM_PATTERNS` | — | JSON array of custom `{name, regex, token}` |

### Access Tracking

| Variable | Default | Description |
|----------|---------|-------------|
| `ACCESS_BOOST_FACTOR` | `0.05` | Importance boost per access |
| `ACCESS_BOOST_WINDOW_HOURS` | `168` | Access counting window |

### Scheduler

| Variable | Default | Description |
|----------|---------|-------------|
| `SCHEDULER_CONSOLIDATION_INTERVAL` | `3600` | Seconds between consolidation |
| `SCHEDULER_ARCHIVE_INTERVAL` | `7200` | Seconds between archiving |
| `SCHEDULER_RECENCY_INTERVAL` | `1800` | Seconds between recency refresh |
| `SCHEDULER_CLEANUP_INTERVAL` | `3600` | Seconds between cleanup |
| `SCHEDULER_PRUNE_INTERVAL` | `86400` | Seconds between log pruning |
| `SCHEDULER_STALE_THRESHOLD_DAYS` | `90` | Archive memories older than |
| `SCHEDULER_ACCESS_LOG_RETENTION_DAYS` | `90` | Prune logs older than |
| `SCHEDULER_ENABLE_CONSOLIDATION` | `true` | Enable consolidation job |
| `SCHEDULER_ENABLE_ARCHIVE` | `true` | Enable archive job |
| `SCHEDULER_ENABLE_RECENCY` | `true` | Enable recency job |
| `SCHEDULER_ENABLE_CLEANUP` | `true` | Enable cleanup job |
| `SCHEDULER_ENABLE_PRUNE` | `true` | Enable prune job |

---

## 31. Docker & Deployment

### Quick Start

```bash
cp .env.example .env     # Configure settings
docker compose up -d     # Start Postgres + API
```

API available at `http://localhost:8100`
Explorer UI at `http://localhost:8100/explorer`

### Docker Architecture

The Dockerfile uses a **multi-stage build**:

1. **Node stage** — Builds the React frontend (`frontend/` → static files)
2. **Python builder stage** — Installs Python dependencies into `/opt/venv`
3. **Runtime stage** — Copies venv + frontend build, runs as non-root `appuser`

### Docker Compose Services

| Service | Image | Purpose |
|---------|-------|---------|
| `db` | `pgvector/pgvector:pg16` | PostgreSQL with pgvector extension |
| `app` | Built from Dockerfile | Production API server |
| `app-dev` | Built from Dockerfile | Dev server with --reload + volume mounts (profile: dev) |

### Entrypoint Commands

```bash
docker compose exec app entrypoint.sh serve       # Production (default)
docker compose exec app entrypoint.sh serve-dev   # Dev with hot-reload
docker compose exec app entrypoint.sh migrate     # Run migrations
docker compose exec app entrypoint.sh downgrade   # Rollback migrations
docker compose exec app entrypoint.sh shell       # Python shell
```

### Health Checks

Both `db` and `app` services have health checks:
- **db**: `pg_isready`
- **app**: `curl http://localhost:8100/api/v1/health`

---

## 32. Project Structure

**180+ source files** across the full project:

```
agentmemodb/
├── app/                           # Main application (89 Python files)
│   ├── api/v1/                    # REST routes (20 modules)
│   │   ├── health.py              # Health & version endpoints
│   │   ├── users.py               # User management
│   │   ├── projects.py            # Project management
│   │   ├── runs.py                # Agent run lifecycle
│   │   ├── events.py              # Event recording
│   │   ├── observations.py        # Observation management
│   │   ├── memories.py            # Core memory CRUD + search
│   │   ├── memory_links.py        # Memory relationships
│   │   ├── tasks.py               # Task state machine
│   │   ├── retrieval_logs.py      # Search audit logging
│   │   ├── artifacts.py           # Binary attachments
│   │   ├── api_keys.py            # API key management
│   │   ├── webhooks.py            # Webhook registration
│   │   ├── bulk.py                # Batch upsert + search
│   │   ├── graph.py               # Graph traversal
│   │   ├── consolidation.py       # Dedup + merge
│   │   ├── import_export.py       # JSON import/export
│   │   ├── scheduler.py           # Scheduler controls
│   │   ├── mcp.py                 # MCP endpoint
│   │   └── router.py              # Route aggregator
│   ├── core/                      # Infrastructure (6 modules)
│   │   ├── config.py / __init__.py # 50+ settings via pydantic-settings
│   │   ├── auth.py                # API key auth + hashing
│   │   ├── errors.py              # Exception hierarchy
│   │   ├── metrics.py             # Prometheus counters/gauges
│   │   └── middleware.py          # RequestID, Timing, CORS
│   ├── db/                        # Database layer
│   │   ├── base.py                # SQLAlchemy Base + Vector type
│   │   ├── session.py             # Async engine + session factory
│   ├── models/                    # 17 ORM models (incl. masking_log)
│   ├── repositories/              # 10 data-access repos
│   ├── schemas/                   # 13 Pydantic v2 modules (incl. masking)
│   ├── services/                  # 12 business-logic services (incl. masking)
│   ├── utils/                     # Embeddings, scoring, hashing, PII masking
│   ├── mcp/                       # MCP server (JSON-RPC 2.0)
│   │   ├── server.py              # MCPServer class + routing
│   │   ├── tools.py               # 7 tool definitions + handlers
│   │   └── transport.py           # HTTP+SSE and stdio transports
│   ├── ws/                        # WebSocket
│   │   ├── __init__.py            # ConnectionManager + MemoryEvent
│   │   └── routes.py              # /ws endpoint handler
│   ├── workers/                   # Background jobs
│   │   └── scheduler.py           # MaintenanceScheduler + 5 jobs
│   ├── adapters/                  # Framework integrations
│   │   └── langgraph_store.py     # LangGraph/LangChain adapter
│   ├── sdk/                       # Python client
│   │   └── client.py              # AgentMemoryDBClient (async)
│   ├── static/explorer/           # Built React frontend
│   └── cli.py                     # Click CLI tool
├── agentmemodb/                   # Pip-installable package (7 files)
│   ├── __init__.py                # Client, HttpClient, types, embeddings
│   ├── client.py                  # Embedded Client (SQLite + NumPy)
│   ├── http_client.py             # Remote Client (httpx)
│   ├── store.py                   # SQLiteStore (CRUD + vector search)
│   ├── types.py                   # Memory, SearchResult, MemoryVersion
│   ├── embeddings.py              # DummyEmbedding, OpenAIEmbedding
│   └── masking.py                 # Standalone PII masking engine
├── frontend/                      # React + Vite + Tailwind source
│   ├── src/
│   │   ├── components/            # Layout, StatCard, ScoreBar, MemoryDetail, GraphVisualization
│   │   ├── context/               # AppContext (connection state)
│   │   ├── hooks/                 # useWebSocket
│   │   ├── lib/                   # api.ts, types.ts, utils.ts
│   │   └── pages/                 # Dashboard, Explorer, Graph, Events, Settings
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.js
├── sdks/typescript/               # TypeScript SDK
├── alembic/                       # DB migrations
│   └── versions/                  # 001_initial, 002_auth_webhooks, 003_data_masking
├── migrations/                    # Feature migrations (RLS)
├── tests/                         # Test suite
│   ├── unit/                      # 14 test modules, 270 tests
│   └── integration/               # Postgres-backed tests
├── examples/                      # Demo scripts + notebooks
├── docs/                          # Architecture docs
├── docker/                        # Docker support files
│   ├── entrypoint.sh              # Multi-command entrypoint
│   └── init-db.sql                # Extension setup
├── Dockerfile                     # Multi-stage (Node + Python)
├── docker-compose.yml             # Postgres + App + Dev profile
├── pyproject.toml                 # Python project config
├── Makefile                       # Dev shortcuts
└── README.md
```

---

## 33. Testing

### Test Suite

- **314 unit tests** across 14 test modules — all passing
- **Integration tests** for Postgres-backed operations

### Test Modules

| Module | Tests | What It Covers |
|--------|-------|----------------|
| `test_access_tracking` | 3 | Access logging, batch access, count queries |
| `test_auth` | 7 | Key generation, hashing, prefix matching |
| `test_bulk_api` | 3 | Batch upsert validation, batch search limits |
| `test_consolidation` | 3 | Duplicate detection, merge logic |
| `test_data_masking` | 60 | PII engine patterns, custom regex, mask_dict, get_default_engine, MaskingService, pipeline helpers, schemas, audit model, edge cases |
| `test_extra_providers` | 5 | SentenceTransformer + Ollama config |
| `test_graph_service` | 4 | BFS expand, shortest path |
| `test_import_export` | 3 | Export/import roundtrip |
| `test_memory_upsert` | 5 | Create, update, dedup, versioning |
| `test_metrics` | 4 | Prometheus counter operations |
| `test_middleware` | 3 | Request ID + timing headers |
| `test_new_features` | 68 | MCP server, tools, WebSocket, scheduler, settings, ErrorResponse |
| `test_pip_package` | 111 | Embedded Client, SQLiteStore, types, embeddings, masking, HttpClient, ShortTermMemory (14), LongTermMemory (9), MemoryManager (13), thread_messages (7) |
| `test_scoring` | 7 | Recency decay, authority normalization, final score |
| `test_sdk_client` | 4 | SDK initialization, headers |
| `test_state_transitions` | 24 | All valid + invalid task transitions |

### Running Tests

```bash
python -m pytest tests/unit -v          # Unit tests (no DB needed)
python -m pytest tests/integration -v   # Integration tests (needs Postgres)
make test-unit                           # Via Makefile
```

---

## 34. Pip Package (Embedded & Remote Client)

AgentMemoryDB can be used as a **pip-installable library** — like ChromaDB, LanceDB, or Qdrant — without Docker or PostgreSQL.

### Install

```bash
pip install agentmemodb                # core (SQLite embedded)
pip install agentmemodb[openai]        # + OpenAI embeddings
pip install agentmemodb[all]           # + all embedding providers
```

### Two Modes, One API

#### Embedded Mode (SQLite, zero config)

```python
import agentmemodb

db = agentmemodb.Client()                       # default: ./agentmemodb_data/
db = agentmemodb.Client(path=":memory:")        # in-memory (tests)
db = agentmemodb.Client(path="./my_memories")   # custom directory

# Store memories
db.upsert("user-1", "pref:lang", "User prefers Python", memory_type="semantic")
db.upsert("user-1", "pref:editor", "User uses VS Code")

# Search
results = db.search("user-1", "What programming language?", top_k=5)
for r in results:
    print(f"  {r.key}: {r.content}  (score={r.score:.3f})")

# Get / List / Delete / Count
mem = db.get("user-1", "pref:lang")
all_mems = db.list("user-1", memory_type="semantic")
db.delete("user-1", "pref:lang")
n = db.count("user-1")

db.close()
```

#### Remote Mode (connect to running server)

```python
import agentmemodb

db = agentmemodb.HttpClient("http://localhost:8100", api_key="amdb_...")

# Same API!
db.upsert("user-1", "pref:lang", "User prefers Python")
results = db.search("user-1", "language?")
db.close()
```

### Client API Reference

Both `Client` and `HttpClient` expose the same methods:

| Method | Signature | Description |
|--------|-----------|-------------|
| `upsert` | `(user_id, key, content, *, memory_type, scope, importance, confidence, authority, metadata) → Memory` | Create or update a memory |
| `search` | `(user_id, query, *, top_k, memory_types) → list[SearchResult]` | Semantic search |
| `get` | `(user_id, key) → Memory \| None` | Get by (user_id, key) |
| `get_by_id` | `(memory_id) → Memory \| None` | Get by UUID |
| `list` | `(user_id, *, memory_type, scope, status, limit, offset) → list[Memory]` | List with filters |
| `delete` | `(user_id, key) → bool` | Delete a memory |
| `count` | `(user_id, status) → int` | Count memories |
| `close` | `() → None` | Release resources |

### Embedding Providers

| Provider | Usage | Requires |
|----------|-------|----------|
| **DummyEmbedding** (default) | `Client()` | Nothing (hash-based, no API key) |
| **OpenAIEmbedding** | `Client(embedding_fn=agentmemodb.OpenAIEmbedding(api_key="sk-..."))` | `pip install openai` |
| **Custom** | `Client(embedding_fn=my_fn)` | Any callable matching `EmbeddingFunction` protocol |

### PII Masking

```python
db = agentmemodb.Client(mask_pii=True)
db.upsert("u1", "k", "Email josh@co.com, SSN 123-45-6789")
# Stored as: "Email [EMAIL], SSN [SSN]"
```

### Comparison with Other Libraries

| Feature | AgentMemoryDB | ChromaDB | Mem0 |
|---------|--------------|----------|------|
| Embedded mode | ✅ SQLite | ✅ SQLite | ❌ Server only |
| Server mode | ✅ PostgreSQL + pgvector | ✅ Chroma server | ✅ Platform |
| Typed memories | ✅ 4 types + scopes | ❌ Collections | ✅ Categories |
| Versioning | ✅ Auto content-hash dedup | ❌ | ❌ |
| Event sourcing | ✅ Event → Observation → Memory | ❌ | ❌ |
| Graph links | ✅ BFS + shortest path | ❌ | ❌ |
| PII masking | ✅ Built-in | ❌ | ❌ |
| Short-term memory | ✅ Conversation buffer w/ threads | ❌ | ❌ |
| Long-term memory | ✅ MemoryManager w/ promote() | ❌ | ✅ Basic |
| LangChain integration | ✅ ChatHistory, Retriever, Tool, Memory | ❌ | ✅ |
| LangGraph integration | ✅ Store, Saver, Memory Nodes | ❌ | ❌ |
| MCP server | ✅ Built-in | ❌ | ❌ |
| Task state machine | ✅ Built-in | ❌ | ❌ |
| Hybrid scoring | ✅ 5-signal weighted | ❌ Vector only | ❌ |

### Architecture (Embedded)

```
  agentmemodb.Client()                            agentmemodb.MemoryManager()
       │                                              │
       ├── EmbeddingFunction (Dummy / OpenAI / HF)    ├── ShortTermMemory  (thread_messages table)
       ├── PIIMaskingEngine (optional)                 ├── LongTermMemory   (wraps Client)
       └── SQLiteStore                                 ├── promote()        (short → long)
              ├── memories table                       └── get_context_window(query)
              ├── memory_versions table
              ├── thread_messages table
              └── NumPy cosine similarity
```

### Package Files

```
agentmemodb/
├── __init__.py                # Client, HttpClient, MemoryManager, types, embeddings
├── client.py                  # Embedded Client (SQLite + NumPy)
├── http_client.py             # Remote Client (httpx)
├── store.py                   # SQLiteStore (CRUD + vector search + thread_messages)
├── types.py                   # Memory, SearchResult, MemoryVersion dataclasses
├── embeddings.py              # DummyEmbedding, OpenAIEmbedding, EmbeddingFunction protocol
├── masking.py                 # Standalone PII masking engine
├── memory_manager.py          # ShortTermMemory, LongTermMemory, MemoryManager
├── py.typed                   # PEP 561 typed marker
└── integrations/
    ├── __init__.py            # Integration exports
    ├── langchain.py           # ChatHistory, Retriever, Tool, ConversationMemory
    └── langgraph.py           # Store, Saver, Memory Nodes
```

---

## 35. Short-Term & Long-Term Memory (MemoryManager)

The `MemoryManager` class provides a unified interface for **short-term conversation memory** and **long-term knowledge storage**, available in the pip package without any server.

### ShortTermMemory

A per-thread conversation buffer backed by the `thread_messages` SQLite table:

```python
from agentmemodb import MemoryManager

mgr = MemoryManager("user-1")

# Add messages (conversation buffer)
mgr.short_term.add_system("You are a helpful assistant.")
mgr.short_term.add_user("I'm building a REST API.")
mgr.short_term.add_assistant("Great! What framework?")
mgr.short_term.add_tool("FastAPI docs loaded successfully.")

# Query
messages = mgr.short_term.get_messages(limit=10)           # most recent N
last_3 = mgr.short_term.get_last(3)                         # last 3 messages
user_only = mgr.short_term.get_messages(roles=["user"])      # filter by role

# Export for LLM
openai_format = mgr.short_term.to_list()                     # [{"role": "...", "content": "..."}]
text_format = mgr.short_term.to_string()                     # "system: ...\nuser: ...\n..."

# Thread management
mgr.short_term.count()                                       # message count
mgr.short_term.clear()                                       # clear current thread
mgr.new_thread("session-2")                                  # start new conversation
```

### LongTermMemory

Persistent semantic knowledge store backed by the embedded Client:

```python
# Store knowledge with importance/confidence
mgr.long_term.remember("pref:lang", "User prefers Python", importance=0.9, confidence=0.95)
mgr.long_term.remember("skill:ml", "Experienced with embeddings and RAG")

# Semantic recall
results = mgr.long_term.recall("What programming language?", top_k=5)
for r in results:
    print(f"  {r.key}: {r.content}  (score={r.score:.3f})")

# CRUD
mem = mgr.long_term.get("pref:lang")
all_mems = mgr.long_term.list_all()
mgr.long_term.forget("pref:lang")
n = mgr.long_term.count()
```

### MemoryManager (Unified)

Combines both with promotion and context windows:

```python
with MemoryManager("user-1", embedding_fn=my_embedding) as mgr:
    # .short_term and .long_term properties
    mgr.short_term.add_user("How to deploy FastAPI?")
    mgr.long_term.remember("pref:deploy", "User prefers Docker")

    # Promote conversation insight → long-term knowledge
    mgr.promote("insight:deploy", "Use Docker + Gunicorn for FastAPI deployment")

    # Combined context window for LLM calls
    ctx = mgr.get_context_window(
        "How should I deploy?",
        n_messages=10,    # recent conversation messages
        n_memories=5,     # relevant long-term memories
    )
    # ctx = {
    #     "messages": [{"role": "user", "content": "..."}],
    #     "relevant_memories": [{"key": "...", "content": "...", "score": 0.95}],
    #     "stats": {"message_count": 10, "memory_count": 3}
    # }
```

### API Summary

| Class | Method | Description |
|-------|--------|-------------|
| **ShortTermMemory** | `add(role, content)` | Add a message |
| | `add_user(content)` / `add_assistant(content)` | Role-specific helpers |
| | `add_system(content)` / `add_tool(content)` | Role-specific helpers |
| | `get_messages(limit, roles)` | Retrieve messages with filters |
| | `get_last(n)` | Last N messages |
| | `to_list()` | OpenAI-compatible format |
| | `to_string()` | Text format |
| | `count()` / `clear()` / `new_thread()` | Management |
| **LongTermMemory** | `remember(key, content, ...)` | Store knowledge |
| | `recall(query, top_k)` | Semantic search |
| | `get(key)` / `forget(key)` | CRUD |
| | `list_all()` / `count()` | Listing |
| **MemoryManager** | `.short_term` / `.long_term` | Access sub-managers |
| | `promote(key, content)` | Short→long-term |
| | `get_context_window(query)` | Combined LLM context |
| | `new_thread(id)` / `reset()` | Thread management |

---

## 36. LangChain & LangGraph Integrations

The pip package includes built-in integrations for both LangChain and LangGraph, available at `agentmemodb.integrations`.

### LangChain Components

```python
from agentmemodb.integrations.langchain import (
    AgentMemoryDBChatHistory,         # BaseChatMessageHistory
    AgentMemoryDBRetriever,           # BaseRetriever → Documents
    AgentMemoryDBConversationMemory,  # History + relevant knowledge
    create_memory_tool,               # Tool for agent store/recall
)
```

| Component | LangChain Base Class | Description |
|-----------|---------------------|-------------|
| **AgentMemoryDBChatHistory** | `BaseChatMessageHistory` | Stores conversation turns as episodic memories. Drop-in for LangChain chains. |
| **AgentMemoryDBRetriever** | `BaseRetriever` | Semantic search → `Document` objects with `page_content`, `metadata` (key, score, type). |
| **AgentMemoryDBConversationMemory** | — | Combines chat history + relevant long-term memories into `load_memory_variables()`. Returns `{history, relevant_context}`. |
| **create_memory_tool()** | `Tool` | Creates a LangChain Tool that accepts JSON `{"action": "store"/"recall", ...}`. Agents can use this to self-manage memory. |

### LangGraph Components

```python
from agentmemodb.integrations.langgraph import (
    AgentMemoryDBStore,        # Long-term memory for nodes
    AgentMemoryDBSaver,        # Checkpoint persistence
    create_memory_node,        # Recall node for StateGraph
    create_save_memory_node,   # Save node for StateGraph
)
```

| Component | Description |
|-----------|-------------|
| **AgentMemoryDBStore** | `put`/`search`/`search_as_text`/`get`/`delete`/`list`/`count` with namespace support. |
| **AgentMemoryDBSaver** | Checkpoint persistence — `put`/`get`/`get_tuple`/`list_checkpoints`/`delete_thread`. Supports time-travel. |
| **create_memory_node()** | Pre-built recall node: reads `input_key` from state, injects relevant memories into `context_key`. |
| **create_save_memory_node()** | Pre-built save node: reads `content_key` from state and persists to long-term memory. |

### Full Agent Pattern (MemoryManager + LangGraph)

```python
from langgraph.graph import StateGraph, END
from agentmemodb import MemoryManager

mgr = MemoryManager("user-1", embedding_fn=my_embedding)

def load_context(state):
    mgr.short_term.add_user(state["input"])
    ctx = mgr.get_context_window(state["input"], n_messages=10, n_memories=5)
    return {"context": ctx["relevant_memories"], "history": ctx["messages"]}

def respond(state):
    # Call your LLM here with state["context"] + state["history"]
    response = call_llm(state)
    mgr.short_term.add_assistant(response)
    return {"output": response}

graph = StateGraph(AgentState)
graph.add_node("load_context", load_context)
graph.add_node("respond", respond)
graph.add_edge("load_context", "respond")
graph.add_edge("respond", END)
graph.set_entry_point("load_context")

agent = graph.compile()
result = agent.invoke({"input": "What should I use for auth?"})
```

### Install Extras

```bash
pip install agentmemodb[langchain]          # LangChain only
pip install agentmemodb[langgraph]          # LangGraph (includes langchain-core)
pip install agentmemodb[all]                # Everything
```

---

## 37. Publishing to PyPI

The pip package is published to PyPI using a dedicated build system in the `pkg/` directory.

### Build & Publish

```bash
# Prerequisites
pip install build twine

# Build (sdist + wheel)
python pkg/publish.py                       # Build only

# Validate
python pkg/publish.py --check               # Build + twine check

# Publish to TestPyPI first
python pkg/publish.py --test-pypi           # Upload to test.pypi.org

# Publish to real PyPI
python pkg/publish.py --pypi                # Upload to pypi.org

# Clean build artifacts
python pkg/publish.py --clean
```

### PyPI Token Setup

1. Create an account at https://pypi.org (or https://test.pypi.org for testing)
2. Go to **Account Settings → API Tokens → Add API Token**
3. Set the token scope to the `agentmemodb` project (or all projects for first upload)
4. Configure twine with the token:

```bash
# Option A: Environment variables
set TWINE_USERNAME=__token__
set TWINE_PASSWORD=pypi-AgEI...your-token...

# Option B: .pypirc file (~/.pypirc)
[pypi]
username = __token__
password = pypi-AgEI...your-token...

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-AgEI...your-token...
```

### Package Structure

```
pkg/
├── pyproject.toml              # PyPI metadata (lightweight deps: numpy only)
├── README.md                   # PyPI-facing documentation
├── publish.py                  # Build + publish script
├── dist/                       # Built artifacts (after build)
│   ├── agentmemodb-0.1.0-py3-none-any.whl
│   └── agentmemodb-0.1.0.tar.gz
└── _build/                     # Temporary build directory (auto-cleaned)
```

### Install Extras (on PyPI)

| Extra | Install Command | What It Adds |
|-------|----------------|--------------|
| *(core)* | `pip install agentmemodb` | SQLite + NumPy (zero config) |
| `remote` | `pip install agentmemodb[remote]` | + httpx (connect to server) |
| `openai` | `pip install agentmemodb[openai]` | + OpenAI embeddings |
| `huggingface` | `pip install agentmemodb[huggingface]` | + sentence-transformers |
| `langchain` | `pip install agentmemodb[langchain]` | + langchain-core |
| `langgraph` | `pip install agentmemodb[langgraph]` | + langgraph + langchain-core |
| `all` | `pip install agentmemodb[all]` | Everything above |

### Version Bumping

Update the version in **two places** before publishing:

1. `pkg/pyproject.toml` → `version = "X.Y.Z"`
2. `agentmemodb/__init__.py` → `__version__ = "X.Y.Z"`

---

*Generated from AgentMemoryDB v0.1.0 source code — 190+ files, 19 tables, 55+ endpoints, 314 tests.*
