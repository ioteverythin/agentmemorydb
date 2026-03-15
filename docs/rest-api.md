# REST API Reference

**Base URL:** `http://localhost:8100`  
**OpenAPI Docs:** `http://localhost:8100/docs`  
**Content-Type:** `application/json`

All examples use `$USER_ID` — replace with your actual UUID.

---

## Table of Contents

1. [Health & Version](#health--version)
2. [Users](#users)
3. [Projects](#projects)
4. [Agent Runs](#agent-runs)
5. [Events](#events)
6. [Observations](#observations)
7. [Memories — CRUD](#memories--crud)
8. [Memory Search](#memory-search)
9. [Memory Versions](#memory-versions)
10. [Memory Links & Graph](#memory-links--graph)
11. [Bulk Operations](#bulk-operations)
12. [Memory Consolidation](#memory-consolidation)
13. [Import / Export](#import--export)
14. [Webhooks](#webhooks)
15. [API Keys](#api-keys)
16. [Tasks](#tasks)
17. [Data Masking](#data-masking)
18. [Scheduler](#scheduler)
19. [Metrics](#metrics)

---

## Health & Version

### GET /health

```bash
curl http://localhost:8100/health
```

```json
{
  "status": "ok",
  "version": "0.1.0",
  "database": "connected",
  "pgvector": true,
  "embeddings": "sentence-transformers/all-MiniLM-L6-v2"
}
```

### GET /version

```bash
curl http://localhost:8100/version
```

```json
{"version": "0.1.0", "api_version": "v1"}
```

---

## Users

### POST /api/v1/users — Create a user

```bash
curl -s -X POST http://localhost:8100/api/v1/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com"}'
```

```json
{
  "id": "a1b2c3d4-0001-0001-0001-000000000001",
  "name": "Alice",
  "email": "alice@example.com",
  "created_at": "2025-01-01T00:00:00Z"
}
```

### GET /api/v1/users/{user_id}

```bash
curl http://localhost:8100/api/v1/users/$USER_ID
```

---

## Projects

Projects let you scope memories to a specific application, workspace, or task.

### POST /api/v1/projects

```bash
curl -s -X POST http://localhost:8100/api/v1/projects \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"name\": \"Code Assistant\",
    \"description\": \"AI coding assistant project memories\"
  }"
```

```json
{
  "id": "p1b2c3d4-...",
  "user_id": "...",
  "name": "Code Assistant",
  "description": "AI coding assistant project memories",
  "created_at": "2025-01-01T00:00:00Z"
}
```

```bash
export PROJECT_ID="p1b2c3d4-..."
```

### GET /api/v1/projects?user_id={user_id}

```bash
curl "http://localhost:8100/api/v1/projects?user_id=$USER_ID"
```

---

## Agent Runs

Runs group events and observations from a single agent execution session.

### POST /api/v1/runs — Start a run

```bash
curl -s -X POST http://localhost:8100/api/v1/runs \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"agent_name\": \"coding-assistant\",
    \"status\": \"running\",
    \"project_id\": \"$PROJECT_ID\"
  }"
```

```json
{
  "id": "r1b2c3d4-...",
  "user_id": "...",
  "agent_name": "coding-assistant",
  "status": "running",
  "started_at": "2025-01-01T00:00:00Z"
}
```

```bash
export RUN_ID="r1b2c3d4-..."
```

### PATCH /api/v1/runs/{run_id}/complete

```bash
curl -s -X PATCH "http://localhost:8100/api/v1/runs/$RUN_ID/complete" \
  -H "Content-Type: application/json" \
  -d '{"summary": "Helped user debug a Python async issue"}'
```

---

## Events

Events are the raw input for the **Event → Observation → Memory** pipeline.

### POST /api/v1/events — Record an event

| Field | Type | Required | Description |
|---|---|---|---|
| `user_id` | UUID | ✓ | Memory owner |
| `run_id` | UUID | ✓ | Associated run |
| `event_type` | string | ✓ | `user_message`, `assistant_response`, `tool_result`, `system_signal` |
| `content` | string | | The event text |
| `payload` | object | | Structured metadata |
| `source` | string | | e.g. `"slack"`, `"api"` |
| `sequence_number` | int | | Ordering within a run |

```bash
curl -s -X POST http://localhost:8100/api/v1/events \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"run_id\": \"$RUN_ID\",
    \"event_type\": \"user_message\",
    \"content\": \"I prefer to use async/await over callbacks in Python.\",
    \"source\": \"chat\"
  }"
```

```json
{
  "id": "e1b2c3d4-...",
  "run_id": "...",
  "event_type": "user_message",
  "content": "I prefer to use async/await over callbacks in Python.",
  "created_at": "2025-01-01T00:00:00Z"
}
```

```bash
export EVENT_ID="e1b2c3d4-..."
```

### GET /api/v1/events?run_id={run_id}

```bash
curl "http://localhost:8100/api/v1/events?run_id=$RUN_ID"
```

---

## Observations

Observations are structured insights extracted from events.

### POST /api/v1/observations/extract-from-event

Automatically extract observations from a recorded event using AI inference:

```bash
curl -s -X POST http://localhost:8100/api/v1/observations/extract-from-event \
  -H "Content-Type: application/json" \
  -d "{\"event_id\": \"$EVENT_ID\"}"
```

```json
[
  {
    "id": "obs1-...",
    "event_id": "...",
    "observation_type": "preference",
    "content": "User prefers async/await over callbacks",
    "confidence": 0.85,
    "created_at": "2025-01-01T00:00:00Z"
  }
]
```

### POST /api/v1/observations — Manual observation

```bash
curl -s -X POST http://localhost:8100/api/v1/observations \
  -H "Content-Type: application/json" \
  -d "{
    \"event_id\": \"$EVENT_ID\",
    \"user_id\": \"$USER_ID\",
    \"observation_type\": \"preference\",
    \"content\": \"User strongly prefers Python over JavaScript\",
    \"confidence\": 0.95
  }"
```

---

## Memories — CRUD

### POST /api/v1/memories/upsert — Create or update

| Field | Type | Default | Description |
|---|---|---|---|
| `user_id` | UUID | required | Memory owner |
| `memory_key` | string | required | Unique key (e.g. `"pref:language"`) |
| `memory_type` | string | `"semantic"` | `semantic`, `episodic`, `procedural`, `working` |
| `scope` | string | `"user"` | `user`, `project`, `session`, `agent` |
| `content` | string | required | The memory text |
| `embedding` | float[] | auto | Override auto-generated embedding |
| `payload` | object | `null` | Arbitrary JSON metadata |
| `source_type` | string | `"system_inference"` | `human_input`, `agent_inference`, `system_inference`, `external_api`, `reflection`, `consolidated` |
| `authority_level` | int | `1` | 1–4 (4 = highest authority) |
| `confidence` | float | `0.5` | 0.0–1.0 |
| `importance_score` | float | `0.5` | 0.0–1.0 |
| `valid_from` | datetime | `null` | Temporal validity start |
| `valid_to` | datetime | `null` | Temporal validity end |
| `expires_at` | datetime | `null` | Auto-archive timestamp |
| `is_contradiction` | bool | `false` | Flags this as contradicting prior memory |
| `project_id` | UUID | `null` | Scope to a project |

```bash
curl -s -X POST http://localhost:8100/api/v1/memories/upsert \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"memory_key\": \"pref:language\",
    \"memory_type\": \"semantic\",
    \"scope\": \"user\",
    \"content\": \"Alice prefers Python for backend, TypeScript for frontend.\",
    \"importance_score\": 0.85,
    \"confidence\": 0.9,
    \"authority_level\": 2,
    \"source_type\": \"human_input\",
    \"payload\": {\"source\": \"onboarding_form\", \"verified\": true}
  }"
```

**Upserting by key:** If a memory with the same `user_id` + `memory_key` already exists, it is updated and the `version` number increments.

### GET /api/v1/memories — List memories

| Param | Type | Description |
|---|---|---|
| `user_id` | UUID | required |
| `project_id` | UUID | optional filter |
| `memory_type` | string | filter by type |
| `scope` | string | filter by scope |
| `status` | string | `active` (default), `archived`, `retracted` |
| `limit` | int | max 1000 (default 100) |
| `offset` | int | pagination offset |

```bash
# All active memories
curl "http://localhost:8100/api/v1/memories?user_id=$USER_ID"

# Only semantic memories
curl "http://localhost:8100/api/v1/memories?user_id=$USER_ID&memory_type=semantic&limit=20"

# Paginate: page 2
curl "http://localhost:8100/api/v1/memories?user_id=$USER_ID&limit=10&offset=10"
```

### GET /api/v1/memories/{memory_id}

```bash
curl http://localhost:8100/api/v1/memories/$MEMORY_ID
```

### PATCH /api/v1/memories/{memory_id}/status

Valid statuses: `active`, `archived`, `retracted`

```bash
# Archive a memory (soft delete, keeps history)
curl -s -X PATCH "http://localhost:8100/api/v1/memories/$MEMORY_ID/status" \
  -H "Content-Type: application/json" \
  -d '{"status": "archived"}'

# Retract a memory (marks as incorrect/superseded)
curl -s -X PATCH "http://localhost:8100/api/v1/memories/$MEMORY_ID/status" \
  -H "Content-Type: application/json" \
  -d '{"status": "retracted"}'
```

---

## Memory Search

### POST /api/v1/memories/search — Hybrid semantic search

| Field | Type | Default | Description |
|---|---|---|---|
| `user_id` | UUID | required | |
| `query_text` | string | `null` | Natural language query |
| `embedding` | float[] | `null` | Override with pre-computed vector |
| `memory_types` | string[] | `null` | Filter: `["semantic", "procedural"]` |
| `scopes` | string[] | `null` | Filter: `["user", "project"]` |
| `status` | string | `"active"` | |
| `top_k` | int | `10` | 1–100 |
| `min_confidence` | float | `null` | Minimum confidence threshold |
| `min_importance` | float | `null` | Minimum importance threshold |
| `metadata_filter` | object | `null` | Match against `payload` JSON |
| `include_expired` | bool | `false` | Include expired memories |
| `explain` | bool | `false` | Return score breakdown per result |
| `run_id` | UUID | `null` | Log this search to a run |
| `project_id` | UUID | `null` | Scope to project |

```bash
# Basic search
curl -s -X POST http://localhost:8100/api/v1/memories/search \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"query_text\": \"What tools does Alice prefer?\",
    \"top_k\": 5
  }"

# Filtered search with score explanation
curl -s -X POST http://localhost:8100/api/v1/memories/search \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"query_text\": \"programming language preferences\",
    \"memory_types\": [\"semantic\"],
    \"scopes\": [\"user\"],
    \"top_k\": 10,
    \"min_confidence\": 0.7,
    \"min_importance\": 0.5,
    \"explain\": true
  }"
```

**Score Breakdown (`explain: true`):**

```json
{
  "results": [
    {
      "memory": { "id": "...", "content": "..." },
      "score": {
        "final_score": 0.847,
        "vector_score": 0.921,
        "recency_score": 0.95,
        "importance_score": 0.85,
        "authority_score": 0.50,
        "confidence_score": 0.90
      }
    }
  ],
  "total_candidates": 12
}
```

The `final_score` is a weighted combination: vector similarity × recency × importance × authority × confidence.

---

## Memory Versions

Every upsert creates a new version. All previous versions are retained for audit.

### GET /api/v1/memories/{memory_id}/versions

```bash
curl "http://localhost:8100/api/v1/memories/$MEMORY_ID/versions"
```

```json
[
  {
    "version": 3,
    "content": "Alice prefers Python (latest update)",
    "changed_at": "2025-03-01T00:00:00Z"
  },
  {
    "version": 2,
    "content": "Alice prefers Python and TypeScript",
    "changed_at": "2025-02-01T00:00:00Z"
  },
  {
    "version": 1,
    "content": "Alice prefers Python",
    "changed_at": "2025-01-01T00:00:00Z"
  }
]
```

---

## Memory Links & Graph

Memory links create a **typed knowledge graph** connecting related memories.

### POST /api/v1/memories/{memory_id}/links — Create a link

| Link type | Meaning |
|---|---|
| `supports` | This memory supports/reinforces another |
| `contradicts` | This memory contradicts another |
| `derived_from` | This memory was derived/inferred from another |
| `related_to` | General relationship |
| `supersedes` | This memory replaces/updates another |

```bash
curl -s -X POST "http://localhost:8100/api/v1/memories/$MEM_A/links" \
  -H "Content-Type: application/json" \
  -d "{
    \"target_memory_id\": \"$MEM_B\",
    \"link_type\": \"supports\",
    \"description\": \"Both express preference for typed languages\"
  }"
```

### GET /api/v1/memories/{memory_id}/links

```bash
curl "http://localhost:8100/api/v1/memories/$MEMORY_ID/links"
```

### POST /api/v1/graph/expand — BFS graph traversal

Expand outward from a seed memory, discovering all connected nodes:

```bash
curl -s -X POST http://localhost:8100/api/v1/graph/expand \
  -H "Content-Type: application/json" \
  -d "{
    \"seed_memory_id\": \"$MEMORY_ID\",
    \"max_hops\": 2,
    \"max_nodes\": 50,
    \"link_types\": [\"supports\", \"derived_from\"]
  }"
```

```json
{
  "seed_memory_id": "...",
  "nodes": [
    {
      "memory_id": "...",
      "memory_key": "pref:language",
      "content": "Alice prefers Python...",
      "depth": 0,
      "link_type": null,
      "link_direction": null
    },
    {
      "memory_id": "...",
      "memory_key": "skill:python",
      "content": "Alice has 5 years of Python experience",
      "depth": 1,
      "link_type": "supports",
      "link_direction": "outbound"
    }
  ],
  "total_nodes": 6
}
```

| Parameter | Type | Range | Default |
|---|---|---|---|
| `seed_memory_id` | UUID | — | required |
| `max_hops` | int | 1–5 | `2` |
| `link_types` | string[] | — | all types |
| `max_nodes` | int | 1–200 | `50` |
| `include_seed` | bool | — | `true` |

### POST /api/v1/graph/shortest-path

Find the shortest connection path between two memories:

```bash
curl -s -X POST http://localhost:8100/api/v1/graph/shortest-path \
  -H "Content-Type: application/json" \
  -d "{
    \"source_id\": \"$MEM_A\",
    \"target_id\": \"$MEM_B\",
    \"max_depth\": 5
  }"
```

```json
{
  "path": ["uuid-A", "uuid-intermediate", "uuid-B"],
  "path_length": 2
}
```

Returns `null` if no path exists within `max_depth`.

---

## Bulk Operations

### POST /api/v1/bulk/upsert — Batch create/update memories

Up to **100 memories** in a single request:

```bash
curl -s -X POST http://localhost:8100/api/v1/bulk/upsert \
  -H "Content-Type: application/json" \
  -d "{
    \"memories\": [
      {
        \"user_id\": \"$USER_ID\",
        \"memory_key\": \"skill:python\",
        \"memory_type\": \"semantic\",
        \"scope\": \"user\",
        \"content\": \"Alice has 5 years Python experience\",
        \"importance_score\": 0.8
      },
      {
        \"user_id\": \"$USER_ID\",
        \"memory_key\": \"skill:typescript\",
        \"memory_type\": \"semantic\",
        \"scope\": \"user\",
        \"content\": \"Alice knows TypeScript well\",
        \"importance_score\": 0.7
      }
    ]
  }"
```

```json
{
  "results": [...],
  "total": 2,
  "created": 2,
  "updated": 0
}
```

### POST /api/v1/bulk/search — Batch search

Up to **20 queries** in a single request:

```bash
curl -s -X POST http://localhost:8100/api/v1/bulk/search \
  -H "Content-Type: application/json" \
  -d "{
    \"queries\": [
      {\"user_id\": \"$USER_ID\", \"query_text\": \"Python skills\", \"top_k\": 3},
      {\"user_id\": \"$USER_ID\", \"query_text\": \"TypeScript skills\", \"top_k\": 3}
    ]
  }"
```

```json
{
  "results": [
    {"query_index": 0, "results": [...]},
    {"query_index": 1, "results": [...]}
  ]
}
```

---

## Memory Consolidation

### GET /api/v1/consolidation/duplicates

Find near-duplicate memories:

```bash
curl "http://localhost:8100/api/v1/consolidation/duplicates?user_id=$USER_ID"
```

```json
[
  {
    "memory_a": {"id": "...", "content": "Alice prefers Python"},
    "memory_b": {"id": "...", "content": "Alice likes Python"},
    "similarity": 0.94
  }
]
```

### POST /api/v1/consolidation/merge

Merge two memories (keep one, archive the other):

```bash
curl -s -X POST http://localhost:8100/api/v1/consolidation/merge \
  -H "Content-Type: application/json" \
  -d "{
    \"keep_id\": \"$MEM_A\",
    \"archive_id\": \"$MEM_B\",
    \"reason\": \"Duplicate — keeping the more complete version\"
  }"
```

### POST /api/v1/consolidation/auto

Auto-merge all duplicates for a user (uses 0.92 similarity threshold):

```bash
curl -s -X POST "http://localhost:8100/api/v1/consolidation/auto?user_id=$USER_ID"
```

```json
{
  "duplicate_groups_found": 3,
  "memories_merged": 3,
  "message": "Auto-consolidation complete"
}
```

---

## Import / Export

### GET /api/v1/data/export

Export all memories for a user as portable JSON:

```bash
curl "http://localhost:8100/api/v1/data/export?user_id=$USER_ID&include_versions=true&include_links=true" \
  > alice_memories.json
```

```json
{
  "user_id": "...",
  "exported_at": "2025-01-01T00:00:00Z",
  "memories": [...],
  "links": [...],
  "versions": [...]
}
```

| Param | Type | Default | Description |
|---|---|---|---|
| `user_id` | UUID | required | |
| `include_versions` | bool | `true` | Include version history |
| `include_links` | bool | `true` | Include memory links |
| `status` | string | all | Filter by status |

### POST /api/v1/data/import

Import previously exported memories:

```bash
curl -s -X POST http://localhost:8100/api/v1/data/import \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$NEW_USER_ID\",
    \"strategy\": \"upsert\",
    \"data\": $(cat alice_memories.json)
  }"
```

| Strategy | Behavior |
|---|---|
| `upsert` (default) | Create new, update existing (by key) |
| `skip_existing` | Only create new memories, skip duplicates |
| `overwrite` | Replace all existing memories |

---

## Webhooks

Webhooks deliver real-time notifications to your endpoint when memory events occur.

### POST /api/v1/webhooks — Register a webhook

```bash
curl -s -X POST http://localhost:8100/api/v1/webhooks \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"url\": \"https://your-server.com/hooks/memory\",
    \"events\": \"memory.created,memory.updated\",
    \"secret\": \"my-webhook-secret-key\",
    \"max_retries\": 3
  }"
```

| Field | Type | Default | Description |
|---|---|---|---|
| `user_id` | UUID | required | |
| `url` | string | required | Your endpoint URL |
| `events` | string | `"*"` | Comma-separated events or `"*"` for all |
| `secret` | string | `null` | HMAC-SHA256 signing secret |
| `max_retries` | int | `3` | 1–10 |

**Available events:**
- `memory.created`, `memory.updated`, `memory.archived`, `memory.retracted`
- `run.started`, `run.completed`
- `consolidation.completed`

**Webhook payload:**
```json
{
  "event": "memory.created",
  "memory_id": "...",
  "memory_key": "pref:language",
  "user_id": "...",
  "timestamp": "2025-01-01T00:00:00Z"
}
```

**Signature verification** (when `secret` is set):
```python
import hmac, hashlib

def verify_webhook(payload_body: bytes, signature_header: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)
```

### GET /api/v1/webhooks?user_id={user_id}

```bash
curl "http://localhost:8100/api/v1/webhooks?user_id=$USER_ID"
```

### DELETE /api/v1/webhooks/{webhook_id}

```bash
curl -X DELETE "http://localhost:8100/api/v1/webhooks/$WEBHOOK_ID"
```

---

## API Keys

API keys authenticate requests and can be scoped to specific operations.

### POST /api/v1/api-keys — Create an API key

```bash
curl -s -X POST http://localhost:8100/api/v1/api-keys \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"name\": \"production-agent\",
    \"scopes\": \"read,write\",
    \"expires_at\": \"2026-01-01T00:00:00Z\"
  }"
```

```json
{
  "id": "key-uuid-...",
  "name": "production-agent",
  "scopes": "read,write",
  "raw_key": "amdb_abc123xyz...",
  "expires_at": "2026-01-01T00:00:00Z",
  "created_at": "2025-01-01T00:00:00Z"
}
```

> ⚠️ **The `raw_key` is shown only once.** Store it securely.

**Scope values:** `read`, `write`, `admin`, or `*` for all.

### Using an API key

```bash
curl http://localhost:8100/api/v1/memories \
  -H "X-API-Key: amdb_abc123xyz..." \
  -G -d "user_id=$USER_ID"
```

### DELETE /api/v1/api-keys/{key_id} — Revoke a key

```bash
curl -X DELETE "http://localhost:8100/api/v1/api-keys/$KEY_ID"
```

---

## Tasks

Tasks represent units of work tracked through a state machine.

### POST /api/v1/tasks — Create a task

```bash
curl -s -X POST http://localhost:8100/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"title\": \"Summarize meeting notes\",
    \"description\": \"Extract action items and decisions\",
    \"priority\": 2,
    \"run_id\": \"$RUN_ID\"
  }"
```

### PATCH /api/v1/tasks/{task_id}/transition — Transition state

Valid states: `pending` → `in_progress` → `completed` / `failed` / `cancelled`

```bash
curl -s -X PATCH "http://localhost:8100/api/v1/tasks/$TASK_ID/transition" \
  -H "Content-Type: application/json" \
  -d "{
    \"to_state\": \"in_progress\",
    \"reason\": \"Starting processing\",
    \"triggered_by\": \"agent:coding-assistant\"
  }"
```

### GET /api/v1/tasks/{task_id}

```bash
curl "http://localhost:8100/api/v1/tasks/$TASK_ID"
```

```json
{
  "id": "...",
  "title": "Summarize meeting notes",
  "status": "in_progress",
  "priority": 2,
  "transitions": [
    {"from_state": "pending", "to_state": "in_progress", "reason": "Starting processing", "timestamp": "..."}
  ]
}
```

---

## Data Masking

Automatic PII detection and masking before memory storage.

### GET /api/v1/masking/config — View masking configuration

```bash
curl http://localhost:8100/api/v1/masking/config
```

```json
{
  "enabled": true,
  "patterns": ["email", "phone", "ssn", "credit_card", "ip_address", "date_of_birth"],
  "replacement_style": "type_label"
}
```

### POST /api/v1/masking/test — Test masking on text

```bash
curl -s -X POST http://localhost:8100/api/v1/masking/test \
  -H "Content-Type: application/json" \
  -d '{"text": "Contact Alice at alice@example.com or 555-123-4567. Her SSN is 123-45-6789."}'
```

```json
{
  "original_text": "Contact Alice at alice@example.com or 555-123-4567. Her SSN is 123-45-6789.",
  "masked_text": "Contact Alice at [EMAIL] or [PHONE]. Her SSN is [SSN].",
  "was_modified": true,
  "patterns_detected": ["email", "phone", "ssn"],
  "detection_count": 3
}
```

### GET /api/v1/masking/logs — Masking audit log

```bash
curl "http://localhost:8100/api/v1/masking/logs?user_id=$USER_ID&limit=20"
```

### GET /api/v1/masking/stats — Masking statistics

```bash
curl "http://localhost:8100/api/v1/masking/stats?user_id=$USER_ID"
```

```json
{
  "total_masked": 47,
  "by_pattern": {
    "email": 23,
    "phone": 15,
    "ssn": 9
  },
  "last_masked_at": "2025-01-01T00:00:00Z"
}
```

---

## Scheduler

Background jobs that maintain memory quality over time.

### GET /api/v1/scheduler/status

```bash
curl http://localhost:8100/api/v1/scheduler/status
```

```json
{
  "running": true,
  "jobs": [
    {"name": "consolidate_duplicates", "next_run": "2025-01-01T01:00:00Z"},
    {"name": "archive_stale", "next_run": "2025-01-01T02:00:00Z"},
    {"name": "recompute_recency", "next_run": "2025-01-01T03:00:00Z"}
  ]
}
```

### GET /api/v1/scheduler/jobs

```bash
curl http://localhost:8100/api/v1/scheduler/jobs
```

### POST /api/v1/scheduler/run/{job_name} — Trigger a job manually

Available jobs:
- `consolidate_duplicates` — find and merge near-duplicate memories
- `archive_stale` — archive memories that haven't been accessed in 90+ days
- `recompute_recency` — recalculate recency scores for ranking
- `cleanup_expired` — remove memories past their `expires_at` date
- `prune_access_logs` — delete old retrieval/access logs

```bash
# Manually trigger duplicate consolidation
curl -s -X POST "http://localhost:8100/api/v1/scheduler/run/consolidate_duplicates"

# Recompute recency scores
curl -s -X POST "http://localhost:8100/api/v1/scheduler/run/recompute_recency"
```

---

## Metrics

Prometheus-compatible metrics endpoint:

```bash
curl http://localhost:8100/metrics
```

Key metrics exported:
| Metric | Description |
|---|---|
| `agentmemorydb_memories_total` | Total memories by type and status |
| `agentmemorydb_search_duration_seconds` | Histogram of search latencies |
| `agentmemorydb_upsert_duration_seconds` | Histogram of upsert latencies |
| `agentmemorydb_active_users` | Count of users with active memories |
| `agentmemorydb_webhook_deliveries_total` | Webhook deliveries by status |
| `http_requests_total` | HTTP request counts by method and path |

Plug into Grafana with a Prometheus datasource at `http://localhost:8100/metrics`.

---

## Error Responses

All errors follow this format:

```json
{
  "detail": "Memory not found",
  "code": "NOT_FOUND",
  "status_code": 404
}
```

| Status | Meaning |
|---|---|
| `400` | Validation error — check request body |
| `401` | Missing or invalid API key |
| `403` | Insufficient scope for this operation |
| `404` | Resource not found |
| `409` | Conflict (e.g. duplicate key on strict create) |
| `422` | Unprocessable entity — schema error |
| `429` | Rate limit exceeded |
| `500` | Internal server error |
