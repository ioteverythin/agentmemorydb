# Advanced Features

---

## Table of Contents

1. [Event → Observation → Memory Pipeline](#event--observation--memory-pipeline)
2. [Memory Knowledge Graph](#memory-knowledge-graph)
3. [Bulk Operations](#bulk-operations)
4. [Memory Consolidation & Deduplication](#memory-consolidation--deduplication)
5. [Import & Export](#import--export)
6. [Webhooks & Real-Time Notifications](#webhooks--real-time-notifications)
7. [PII Data Masking](#pii-data-masking)
8. [API Key Authentication](#api-key-authentication)
9. [Tasks & State Machine](#tasks--state-machine)
10. [Background Scheduler](#background-scheduler)
11. [Row-Level Security](#row-level-security)
12. [CLI Tool](#cli-tool)
13. [Prometheus Metrics & Monitoring](#prometheus-metrics--monitoring)

---

## Event → Observation → Memory Pipeline

This is AgentMemoryDB's core intelligence pipeline. Raw agent events are automatically processed into structured observations and then into searchable memories.

```
User Message / Tool Result
        ↓
    [Event]        — raw, unstructured log entry
        ↓
  [Observation]    — structured insight extracted from event
        ↓
    [Memory]       — versioned, searchable, scored knowledge
```

### Step 1: Create a Run

A run groups all events from one agent execution session.

```python
import asyncio
from app.sdk.client import AgentMemoryDBClient

async def run_pipeline():
    async with AgentMemoryDBClient("http://localhost:8100") as client:
        # Create user + run
        user = await client.create_user("Alice")
        user_id = user["id"]

        run = await client.create_run(
            user_id=user_id,
            agent_name="my-assistant",
            status="running",
        )
        run_id = run["id"]

        # Step 2: Record events
        event = await client.create_event(
            run_id=run_id,
            user_id=user_id,
            event_type="user_message",
            content="I really love async Python. Callbacks are terrible.",
            source="chat_ui",
        )
        event_id = event["id"]

        # Step 3: Auto-extract observations
        observations = await client.extract_observations(event_id)
        # Returns structured insights:
        # [{"type": "preference", "content": "User strongly prefers async Python over callbacks", "confidence": 0.9}]

        # Step 4: Observations auto-promote to memories
        # (or you can manually store the insight as a memory)
        mem = await client.upsert_memory(
            user_id=user_id,
            memory_key="pref:python_style",
            content="User loves async Python; finds callbacks terrible",
            memory_type="semantic",
            importance_score=0.85,
            confidence=0.9,
            source_type="system_inference",
        )

        # Step 5: Complete the run
        await client.complete_run(run_id, summary="Captured coding preferences")

asyncio.run(run_pipeline())
```

### Event Types

| Type | When to use |
|---|---|
| `user_message` | Human user input |
| `assistant_response` | AI-generated response |
| `tool_result` | Output from a tool call |
| `system_signal` | System-level event (timeout, error, etc.) |

### Observation Types

Observations are the structured layer between raw events and stored memories:

| Type | Example |
|---|---|
| `preference` | "User prefers Python" |
| `fact` | "User is a senior engineer at ACME Corp" |
| `decision` | "User chose PostgreSQL over MySQL" |
| `action` | "User ran test suite successfully" |
| `error` | "User encountered ImportError in module X" |

---

## Memory Knowledge Graph

AgentMemoryDB stores memories as nodes in a typed knowledge graph. Links between memories express relationships like "supports", "contradicts", "derived_from", etc.

### Creating Links

```python
import asyncio
from app.sdk.client import AgentMemoryDBClient

async def build_graph():
    async with AgentMemoryDBClient("http://localhost:8100") as client:
        user_id = "..."  # your user ID

        # Create base memories
        lang_mem = await client.upsert_memory(
            user_id=user_id,
            memory_key="pref:language",
            content="Alice prefers Python for backend development.",
            memory_type="semantic",
            importance_score=0.85,
        )

        skill_mem = await client.upsert_memory(
            user_id=user_id,
            memory_key="skill:python",
            content="Alice has 5 years of Python experience.",
            memory_type="semantic",
            importance_score=0.8,
        )

        # Link: skill "supports" preference
        import httpx
        async with httpx.AsyncClient(base_url="http://localhost:8100") as http:
            await http.post(
                f"/api/v1/memories/{lang_mem['id']}/links",
                json={
                    "target_memory_id": skill_mem["id"],
                    "link_type": "supports",
                    "description": "Experience supports the preference",
                }
            )

asyncio.run(build_graph())
```

### Link Types Reference

| Type | Direction | Meaning |
|---|---|---|
| `supports` | A → B | A provides evidence for B |
| `contradicts` | A → B | A conflicts with B |
| `derived_from` | A → B | A was inferred/derived from B |
| `related_to` | A ↔ B | General undirected relationship |
| `supersedes` | A → B | A is a newer/better version of B |

### Graph Expansion (BFS Traversal)

```bash
# Expand 2 hops from a seed memory
curl -s -X POST http://localhost:8100/api/v1/graph/expand \
  -H "Content-Type: application/json" \
  -d '{
    "seed_memory_id": "YOUR-MEMORY-UUID",
    "max_hops": 2,
    "max_nodes": 50
  }'
```

```python
# SDK
graph = await client.expand_graph(
    seed_memory_id=memory_id,
    max_hops=2,
    max_nodes=50,
    link_types=["supports", "derived_from"],  # filter to specific link types
)

print(f"Total nodes: {graph['total_nodes']}")
for node in graph["nodes"]:
    depth = node["depth"]
    indent = "  " * depth
    print(f"{indent}[depth={depth}] {node['memory_key']}: {node['content'][:60]}")
    if node["link_type"]:
        print(f"{indent}  via {node['link_direction']} {node['link_type']}")
```

### Shortest Path

Find how two memories are connected:

```bash
curl -s -X POST http://localhost:8100/api/v1/graph/shortest-path \
  -H "Content-Type: application/json" \
  -d '{
    "source_id": "UUID-A",
    "target_id": "UUID-B",
    "max_depth": 5
  }'
```

```json
{
  "path": ["uuid-A", "uuid-intermediate-1", "uuid-B"],
  "path_length": 2
}
```

Returns `{"path": null, "path_length": null}` if no path exists.

### Use Cases for Memory Graphs

- **Contradiction detection**: Link contradicting memories; filter by `link_type=contradicts` to find conflicts
- **Knowledge provenance**: Trace `derived_from` links to understand how a belief was formed
- **Related context**: Use graph expansion to surface supporting memories during retrieval
- **Belief updates**: When a fact changes, use `supersedes` to mark the old memory

---

## Bulk Operations

Process up to 100 memories or 20 searches in a single API call.

### Batch Upsert

```python
# SDK
result = await client.batch_upsert([
    {
        "user_id": user_id,
        "memory_key": f"skill:{i}",
        "memory_type": "semantic",
        "scope": "user",
        "content": f"Skill number {i} description",
        "importance_score": 0.6 + (i * 0.01),
    }
    for i in range(50)
])
print(f"Created: {result['created']}, Updated: {result['updated']}")
```

```bash
# REST
curl -s -X POST http://localhost:8100/api/v1/bulk/upsert \
  -H "Content-Type: application/json" \
  -d '{
    "memories": [
      {"user_id": "...", "memory_key": "skill:python", "memory_type": "semantic", "scope": "user", "content": "Python expert"},
      {"user_id": "...", "memory_key": "skill:docker", "memory_type": "semantic", "scope": "user", "content": "Docker proficient"}
    ]
  }'
```

### Batch Search

Run multiple independent searches in one round trip:

```python
results = await client.batch_search([
    {"user_id": user_id, "query_text": "Python skills", "top_k": 5, "explain": True},
    {"user_id": user_id, "query_text": "DevOps preferences", "top_k": 3},
    {"user_id": user_id, "query_text": "past meeting notes", "memory_types": ["episodic"], "top_k": 5},
])

for i, query_result in enumerate(results["results"]):
    print(f"\nQuery {i}: {len(query_result['results'])} results")
    for r in query_result["results"]:
        print(f"  {r['memory']['memory_key']}: {r['memory']['content'][:60]}")
```

### Performance Note

Bulk upsert processes all memories concurrently with automatic embedding generation. For 100 memories with `all-MiniLM-L6-v2`:
- ~0.5–1.5 seconds for embedding generation (CPU)
- ~50–100ms for database writes
- Total: **under 2 seconds for 100 memories**

---

## Memory Consolidation & Deduplication

Over time, agents may store near-duplicate memories. The consolidation system detects and merges them automatically.

### Detect Duplicates

```bash
curl "http://localhost:8100/api/v1/consolidation/duplicates?user_id=$USER_ID"
```

```json
[
  {
    "memory_a": {
      "id": "uuid-a",
      "memory_key": "pref:language",
      "content": "Alice prefers Python"
    },
    "memory_b": {
      "id": "uuid-b",
      "memory_key": "pref:lang",
      "content": "Alice likes Python for coding"
    },
    "similarity": 0.94
  }
]
```

### Manual Merge

```bash
curl -s -X POST http://localhost:8100/api/v1/consolidation/merge \
  -H "Content-Type: application/json" \
  -d '{
    "keep_id": "uuid-a",
    "archive_id": "uuid-b",
    "reason": "Keeping more complete version with better key naming"
  }'
```

The archived memory gets `status: "archived"` and its content is linked to the surviving memory via a `supersedes` link.

### Auto-Consolidation

```bash
# Merge all detected duplicates automatically (similarity threshold: 0.92)
curl -s -X POST "http://localhost:8100/api/v1/consolidation/auto?user_id=$USER_ID"
```

```json
{
  "duplicate_groups_found": 4,
  "memories_merged": 4,
  "message": "Auto-consolidation complete"
}
```

### Via SDK

```python
# Find duplicates
duplicates = await client.find_duplicates(user_id)
print(f"Found {len(duplicates)} duplicate pairs")

# Auto-consolidate
result = await client.auto_consolidate(user_id)
print(f"Merged {result['memories_merged']} memories")
```

### Scheduled Consolidation

The scheduler runs `consolidate_duplicates` automatically on a configurable interval. Trigger it manually:

```bash
curl -s -X POST http://localhost:8100/api/v1/scheduler/run/consolidate_duplicates
```

---

## Import & Export

Portable JSON export/import for backup, migration, and multi-environment sync.

### Export

```bash
# Export all memories with full history
curl "http://localhost:8100/api/v1/data/export?user_id=$USER_ID&include_versions=true&include_links=true" \
  > backup.json

# Export only active semantic memories
curl "http://localhost:8100/api/v1/data/export?user_id=$USER_ID&status=active" \
  > active_memories.json
```

Export format:
```json
{
  "user_id": "...",
  "exported_at": "2025-01-01T00:00:00Z",
  "total_memories": 47,
  "memories": [
    {
      "memory_key": "pref:language",
      "memory_type": "semantic",
      "content": "Alice prefers Python",
      "importance_score": 0.85,
      "confidence": 0.9,
      "version": 3,
      "payload": {...}
    }
  ],
  "links": [...],
  "versions": [...]
}
```

### Import

```bash
# Import into a new user (upsert strategy — create new, update existing)
curl -s -X POST http://localhost:8100/api/v1/data/import \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$NEW_USER_ID\",
    \"strategy\": \"upsert\",
    \"data\": $(cat backup.json)
  }"
```

| Strategy | Effect |
|---|---|
| `upsert` | Create new memories, update existing ones by key |
| `skip_existing` | Only create memories with keys that don't already exist |
| `overwrite` | Replace all existing memories entirely |

### Python Example

```python
import json

# Export
export_data = await client.export_memories(
    user_id=user_id,
    include_versions=True,
    include_links=True,
)

# Save to file
with open("memories_backup.json", "w") as f:
    json.dump(export_data, f, indent=2)

# Restore to another user
with open("memories_backup.json") as f:
    data = json.load(f)

result = await client.import_memories(
    user_id=new_user_id,
    data=data,
    strategy="upsert",
)
print(f"Imported: {result['total_imported']} memories")
```

---

## Webhooks & Real-Time Notifications

Webhooks push events to your server the moment something changes.

### Register a Webhook

```bash
curl -s -X POST http://localhost:8100/api/v1/webhooks \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "USER-UUID",
    "url": "https://your-server.com/memory-events",
    "events": "memory.created,memory.updated,memory.archived",
    "secret": "my-webhook-signing-secret",
    "max_retries": 3
  }'
```

### Available Events

| Event | Trigger |
|---|---|
| `memory.created` | New memory stored |
| `memory.updated` | Memory content updated (new version) |
| `memory.archived` | Memory status set to `archived` |
| `memory.retracted` | Memory status set to `retracted` |
| `run.started` | Agent run created |
| `run.completed` | Agent run completed |
| `consolidation.completed` | Auto-consolidation job finished |

Use `"*"` for all events.

### Webhook Payload

```json
{
  "event": "memory.created",
  "memory_id": "9086d314-...",
  "memory_key": "pref:language",
  "memory_type": "semantic",
  "user_id": "a1b2c3...",
  "timestamp": "2025-01-01T12:00:00Z",
  "version": 1
}
```

### Signature Verification

When a `secret` is set, each webhook request includes an `X-Signature-256` header:

```python
# FastAPI webhook receiver with signature verification
import hmac
import hashlib
from fastapi import FastAPI, Request, HTTPException

app = FastAPI()
WEBHOOK_SECRET = "my-webhook-signing-secret"

@app.post("/memory-events")
async def receive_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Signature-256", "")

    # Verify
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event = payload["event"]
    memory_id = payload.get("memory_id")

    if event == "memory.created":
        print(f"New memory created: {memory_id}")
    elif event == "memory.updated":
        print(f"Memory updated: {memory_id} (v{payload.get('version')})")

    return {"received": True}
```

### Retry Logic

Failed webhook deliveries are automatically retried with exponential backoff (up to `max_retries` times). View delivery history at `GET /api/v1/webhooks/{id}/deliveries`.

---

## PII Data Masking

AgentMemoryDB automatically detects and masks personally identifiable information before storing memories.

### Enabling Masking

**Per-client (embedded):**
```python
db = agentmemodb.Client(mask_pii=True)
```

**Server-side:** Set `MASKING_ENABLED=true` in environment:
```yaml
# docker-compose.yml
environment:
  - MASKING_ENABLED=true
  - MASKING_PATTERNS=email,phone,ssn,credit_card,ip_address
```

### Detected PII Patterns

| Pattern | Example | Masked As |
|---|---|---|
| Email | `alice@example.com` | `[EMAIL]` |
| Phone | `555-123-4567` | `[PHONE]` |
| SSN | `123-45-6789` | `[SSN]` |
| Credit card | `4111-1111-1111-1111` | `[CREDIT_CARD]` |
| IP address | `192.168.1.100` | `[IP_ADDRESS]` |
| Date of birth | `DOB: 01/15/1990` | `[DATE_OF_BIRTH]` |

### Test Masking

```bash
curl -s -X POST http://localhost:8100/api/v1/masking/test \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Contact Alice at alice@example.com or call 555-123-4567. Card: 4111-1111-1111-1111"
  }'
```

```json
{
  "original_text": "Contact Alice at alice@example.com or call 555-123-4567. Card: 4111-1111-1111-1111",
  "masked_text": "Contact Alice at [EMAIL] or call [PHONE]. Card: [CREDIT_CARD]",
  "was_modified": true,
  "patterns_detected": ["email", "phone", "credit_card"],
  "detection_count": 3
}
```

### Audit Logs

Every masking event is logged for compliance:

```bash
# View masking logs
curl "http://localhost:8100/api/v1/masking/logs?user_id=$USER_ID&limit=20"

# Masking statistics
curl "http://localhost:8100/api/v1/masking/stats?user_id=$USER_ID"
```

### Custom Patterns

Add custom regex patterns via the config endpoint or environment variable:

```bash
# View current config
curl http://localhost:8100/api/v1/masking/config
```

---

## API Key Authentication

### Create an API Key

```bash
curl -s -X POST http://localhost:8100/api/v1/api-keys \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "USER-UUID",
    "name": "production-agent-v1",
    "scopes": "read,write",
    "expires_at": "2026-01-01T00:00:00Z"
  }'
```

> ⚠️ Copy the `raw_key` immediately — it's shown only once.

### Scopes

| Scope | Allowed Operations |
|---|---|
| `read` | GET requests (list, search, get) |
| `write` | POST/PATCH/PUT (create, update) |
| `admin` | DELETE, key management, scheduler |
| `*` | All operations |

### Using API Keys

```bash
# Header method (preferred)
curl http://localhost:8100/api/v1/memories \
  -H "X-API-Key: amdb_abc123..." \
  -G -d "user_id=$USER_ID"

# Bearer token method
curl http://localhost:8100/api/v1/memories \
  -H "Authorization: Bearer amdb_abc123..." \
  -G -d "user_id=$USER_ID"
```

```python
# In the async SDK
async with AgentMemoryDBClient(
    base_url="http://localhost:8100",
    api_key="amdb_abc123...",
) as client:
    ...
```

### Revoking Keys

```bash
curl -X DELETE "http://localhost:8100/api/v1/api-keys/$KEY_ID"
```

---

## Tasks & State Machine

Tasks track units of agent work with a formal state machine and full transition history.

### State Transitions

```
        pending
           │
    ┌──────┴──────┐
    │             │
in_progress    cancelled
    │
    ├──── completed
    └──── failed
```

### Creating and Tracking Tasks

```python
# Create
task = await client.create_task(
    user_id=user_id,
    title="Extract meeting action items",
    description="Process the 2025-01-01 meeting transcript",
    priority=2,   # higher = more important
    run_id=run_id,
)
task_id = task["id"]

# Start processing
await client.transition_task(
    task_id=task_id,
    to_state="in_progress",
    reason="Processing started",
    triggered_by="agent:extractor",
)

# Complete
await client.transition_task(
    task_id=task_id,
    to_state="completed",
    reason="Extracted 5 action items",
)

# Query
task_status = await client.get_task(task_id)
print(task_status["status"])        # "completed"
print(task_status["transitions"])   # full history
```

```bash
# REST
curl "http://localhost:8100/api/v1/tasks?user_id=$USER_ID&status=in_progress"
```

---

## Background Scheduler

The scheduler runs background maintenance jobs on a configurable schedule.

### Available Jobs

| Job | What it does | Default Schedule |
|---|---|---|
| `consolidate_duplicates` | Find and merge near-duplicate memories | Every 6 hours |
| `archive_stale` | Archive memories not accessed in 90+ days | Daily at 2am |
| `recompute_recency` | Recalculate recency scores for ranking | Every hour |
| `cleanup_expired` | Remove memories past `expires_at` | Every 30 minutes |
| `prune_access_logs` | Delete old retrieval/access logs (keep 30d) | Daily at 3am |

### Check Status

```bash
curl http://localhost:8100/api/v1/scheduler/status
```

```json
{
  "running": true,
  "jobs": [
    {
      "name": "consolidate_duplicates",
      "next_run": "2025-01-01T06:00:00Z",
      "last_run": "2025-01-01T00:00:00Z",
      "last_duration_ms": 342
    }
  ]
}
```

### Trigger Manually

```bash
# Run deduplication now
curl -s -X POST http://localhost:8100/api/v1/scheduler/run/consolidate_duplicates

# Archive stale memories now
curl -s -X POST http://localhost:8100/api/v1/scheduler/run/archive_stale

# Recompute all recency scores
curl -s -X POST http://localhost:8100/api/v1/scheduler/run/recompute_recency

# Clean up expired memories
curl -s -X POST http://localhost:8100/api/v1/scheduler/run/cleanup_expired

# Prune old access logs
curl -s -X POST http://localhost:8100/api/v1/scheduler/run/prune_access_logs
```

---

## Row-Level Security

AgentMemoryDB implements row-level security (RLS) at the service layer:

- **User isolation**: All queries are automatically scoped to `user_id` — a user can never read another user's memories
- **Project scoping**: When `project_id` is provided, memories are further filtered by project membership
- **API key scopes**: Read-only keys cannot write; write keys cannot delete; admin-only operations require `admin` scope
- **Webhook isolation**: Webhooks only fire for events belonging to the registered `user_id`

### Multi-Tenant Example

```python
# Each tenant has their own user_id
tenant_a = "tenant-a-uuid"
tenant_b = "tenant-b-uuid"

# Memories are completely isolated
await client.upsert_memory(tenant_a, "data:secret", "Tenant A's private data", ...)
await client.upsert_memory(tenant_b, "data:secret", "Tenant B's private data", ...)

# Searching as tenant_a NEVER returns tenant_b's memories
results = await client.search_memories(tenant_a, "secret data")
# Always returns only tenant_a's memories
```

---

## CLI Tool

The CLI provides operational commands for DBAs, devs, and CI/CD pipelines.

```bash
# Inside Docker container
docker exec agentmemodb-app-1 python -m app.cli --help

# If running locally
python -m app.cli --help
```

### Available Commands

```bash
# Check database health
python -m app.cli health

# Show memory statistics for a user
python -m app.cli stats --user-id a1b2c3d4-...

# Export memories to JSON file
python -m app.cli export --user-id a1b2c3d4-... --output ./backup.json

# Import memories from JSON file
python -m app.cli import --user-id a1b2c3d4-... --input ./backup.json

# Auto-consolidate duplicates for a user
python -m app.cli consolidate --user-id a1b2c3d4-...

# Archive all stale memories (not accessed in 90+ days)
python -m app.cli archive-stale

# Recompute recency scores for all memories
python -m app.cli recompute-recency
```

### Example: Stats Output

```
📊 Memory Statistics for user a1b2c3d4…

  Total memories:    47

  By status:
    active:          42
    archived:         4
    retracted:        1

  By type:
    semantic:        28
    episodic:        12
    procedural:       5
    working:          2

  By scope:
    user:            35
    project:          8
    session:          4

  Avg importance:    0.72
  Avg confidence:    0.84
  Avg recency:       0.91
```

---

## Prometheus Metrics & Monitoring

### Metrics Endpoint

```bash
curl http://localhost:8100/metrics
```

### Key Metrics

```
# Memory counts by type and status
agentmemorydb_memories_total{memory_type="semantic",status="active"} 247

# Search performance
agentmemorydb_search_duration_seconds_bucket{le="0.1"} 1453
agentmemorydb_search_duration_seconds_bucket{le="0.5"} 1498
agentmemorydb_search_duration_seconds_p99 0.087

# Upsert performance  
agentmemorydb_upsert_duration_seconds_p99 0.043

# Webhook deliveries
agentmemorydb_webhook_deliveries_total{status="success"} 124
agentmemorydb_webhook_deliveries_total{status="failed"} 2

# Active users
agentmemorydb_active_users 38

# HTTP request rates
http_requests_total{method="POST",path="/api/v1/memories/search",status="200"} 8921
```

### Grafana Dashboard

Set up a Grafana instance with Prometheus datasource pointing to `http://localhost:8100/metrics`. Recommended panels:

1. **Search latency** — P50/P95/P99 over time
2. **Memory growth** — Total memories by type
3. **Active users** — Gauge with threshold alerts
4. **Error rate** — HTTP 4xx/5xx over time
5. **Webhook delivery rate** — Success vs failure

### Health Check for Load Balancers

```bash
# Returns 200 only when fully healthy
curl http://localhost:8100/health
# Returns 200 when database is connected (liveness)
curl http://localhost:8100/ping
```

Use `/health` for readiness probe and `/ping` for liveness probe in Kubernetes deployments.
