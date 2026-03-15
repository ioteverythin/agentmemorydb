# AgentMemoryDB — Complete Usage Guide

> **Practical reference with working examples for every feature.**  
> Assumes the server is running at `http://localhost:8100`. See [Docker & Deployment](#29-docker--deployment) to get started.

---

## Table of Contents

1. [Quick Start (5 minutes)](#1-quick-start-5-minutes)
2. [Core Concepts](#2-core-concepts)
3. [REST API — curl Examples](#3-rest-api--curl-examples)
4. [Python Embedded Client](#4-python-embedded-client)
5. [Python HTTP Client](#5-python-http-client)
6. [TypeScript SDK](#6-typescript-sdk)
7. [MemoryManager — Short-Term & Long-Term](#7-memorymanager--short-term--long-term)
8. [Event → Observation → Memory Pipeline](#8-event--observation--memory-pipeline)
9. [Hybrid Search — All Options](#9-hybrid-search--all-options)
10. [Memory Graph — Links, BFS, Shortest Path](#10-memory-graph--links-bfs-shortest-path)
11. [Memory Versioning & Deduplication](#11-memory-versioning--deduplication)
12. [Task State Machine](#12-task-state-machine)
13. [MCP Server — JSON-RPC Examples](#13-mcp-server--json-rpc-examples)
14. [WebSocket — Real-Time Events](#14-websocket--real-time-events)
15. [LangChain Integration](#15-langchain-integration)
16. [LangGraph Integration](#16-langgraph-integration)
17. [Bulk Operations](#17-bulk-operations)
18. [Import & Export](#18-import--export)
19. [Memory Consolidation](#19-memory-consolidation)
20. [PII Data Masking](#20-pii-data-masking)
21. [Authentication & API Keys](#21-authentication--api-keys)
22. [Row Level Security](#22-row-level-security)
23. [Webhooks](#23-webhooks)
24. [Scheduled Maintenance](#24-scheduled-maintenance)
25. [Observability](#25-observability)
26. [Access Tracking](#26-access-tracking)
27. [CLI Tool](#27-cli-tool)
28. [Explorer UI](#28-explorer-ui)
29. [Docker & Deployment](#29-docker--deployment)
30. [Configuration Reference](#30-configuration-reference)

---

## 1. Quick Start (5 minutes)

### Option A — Docker (full server with PostgreSQL + pgvector)

```bash
# 1. Clone and start
git clone https://github.com/ioteverythin/agentmemorydb.git
cd agentmemorydb

# 2. Start containers
docker compose up -d

# 3. Verify
curl http://localhost:8100/api/v1/health
# {"status":"ok","version":"0.1.0"}

# 4. Open the Explorer UI
# http://localhost:8100/explorer
```

### Option B — Pip package (zero-config embedded SQLite)

```bash
pip install agentmemodb

python - <<'EOF'
import agentmemodb

db = agentmemodb.Client()
db.upsert("alice", "pref:lang", "User prefers Python", memory_type="semantic")
results = db.search("alice", "What programming language does the user prefer?")
for r in results:
    print(r.key, r.score, r.content)
db.close()
EOF
```

### Create your first memory via curl

```bash
# Step 1 — create a user
curl -s -X POST http://localhost:8100/api/v1/users \
  -H "Content-Type: application/json" \
  -d '{"display_name": "Alice"}' | python -m json.tool

# Step 2 — store a memory (replace USER_ID with the id from step 1)
export USER_ID="<paste-uuid-here>"

curl -s -X POST http://localhost:8100/api/v1/memories/upsert \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"memory_key\": \"pref:language\",
    \"memory_type\": \"semantic\",
    \"content\": \"User prefers Python for backend work\"
  }" | python -m json.tool

# Step 3 — search
curl -s -X POST http://localhost:8100/api/v1/memories/search \
  -H "Content-Type: application/json" \
  -d "{\"user_id\": \"$USER_ID\", \"query_text\": \"programming language\"}" \
  | python -m json.tool
```

---

## 2. Core Concepts

| Concept | Description |
|---------|-------------|
| **User** | An entity (human or agent) whose memories are stored. Every memory belongs to a user. |
| **Project** | Optional multi-tenant namespace. Memories can be scoped to a project. |
| **Agent Run** | A discrete execution session. Links events, observations, and memories to one run. |
| **Event** | Raw input captured during a run (user message, tool result, function call, etc.). |
| **Observation** | A structured fact extracted from an event — the bridge between raw data and memory. |
| **Memory** | A versioned, searchable knowledge record with a composite score. |
| **Memory Key** | A namespaced string identifier (e.g. `pref:language`, `fact:employer`). Keys are unique per user+scope. |
| **Memory Type** | `semantic` (facts/preferences), `episodic` (events), `procedural` (skills), `working` (temporary). |
| **Memory Scope** | `user`, `session`, `project`, or `global` — controls visibility. |
| **Memory Status** | `active`, `archived`, `deprecated`, `conflicted`. |
| **Memory Link** | A typed directed edge between two memories (supports, contradicts, derived_from, etc.). |
| **Task** | A unit of work with a formal state machine (pending → in_progress → completed). |
| **Artifact** | Binary/file attachment associated with a memory or run. |

### Composite Score Formula

Every search result has a composite score from 5 signals:

$$\text{score} = 0.45 \cdot v + 0.20 \cdot r + 0.15 \cdot i + 0.10 \cdot a + 0.10 \cdot c$$

Where $v$ = vector similarity, $r$ = recency, $i$ = importance, $a$ = authority, $c$ = confidence.  
Working memory bypasses recency decay. Global-scope memories get a $1.5\times$ authority boost.

---

## 3. REST API — curl Examples

All endpoints live under `http://localhost:8100/api/v1`.

> **Authentication**: When `REQUIRE_AUTH=true`, add `-H "X-API-Key: amdb_..."` to every request.

### 3.1 Health & System

```bash
# Basic health check
curl http://localhost:8100/api/v1/health

# Deep health (DB + pgvector + memory count)
curl http://localhost:8100/api/v1/health/deep

# Version + feature flags
curl http://localhost:8100/api/v1/version

# Prometheus metrics
curl http://localhost:8100/metrics
```

### 3.2 Users

```bash
# Create a user
curl -s -X POST http://localhost:8100/api/v1/users \
  -H "Content-Type: application/json" \
  -d '{"display_name": "Alice", "metadata": {"team": "engineering"}}'

# Get a user by ID
curl http://localhost:8100/api/v1/users/$USER_ID
```

### 3.3 Projects

```bash
# Create a project
curl -s -X POST http://localhost:8100/api/v1/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "my-agent", "description": "Production agent project"}'

# List all projects
curl http://localhost:8100/api/v1/projects
```

### 3.4 Agent Runs

```bash
# Create a run (attach to user + project)
curl -s -X POST http://localhost:8100/api/v1/runs \
  -H "Content-Type: application/json" \
  -d "{\"user_id\": \"$USER_ID\", \"project_id\": \"$PROJECT_ID\"}"

# Mark run as completed
curl -s -X PATCH http://localhost:8100/api/v1/runs/$RUN_ID/complete
```

### 3.5 Events

```bash
# Record a raw event (user message)
curl -s -X POST http://localhost:8100/api/v1/events \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"run_id\": \"$RUN_ID\",
    \"event_type\": \"user_message\",
    \"content\": \"I love hiking in the mountains on weekends.\",
    \"payload\": {\"session\": \"chat-001\"}
  }"

# List events for a user
curl "http://localhost:8100/api/v1/events?user_id=$USER_ID&limit=20"
```

### 3.6 Observations

```bash
# Record an observation extracted from an event
curl -s -X POST http://localhost:8100/api/v1/observations \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"source_event_id\": \"$EVENT_ID\",
    \"observation_type\": \"preference\",
    \"content\": \"User enjoys hiking outdoors\",
    \"confidence\": 0.9
  }"

# Auto-extract observations from an event (LLM-free rule engine)
curl -s -X POST http://localhost:8100/api/v1/observations/extract-from-event \
  -H "Content-Type: application/json" \
  -d "{\"event_id\": \"$EVENT_ID\"}"

# List observations
curl "http://localhost:8100/api/v1/observations?user_id=$USER_ID"
```

### 3.7 Memories — CRUD

```bash
# Create / update a memory (upsert by memory_key)
curl -s -X POST http://localhost:8100/api/v1/memories/upsert \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"memory_key\": \"hobby:hiking\",
    \"memory_type\": \"semantic\",
    \"scope\": \"user\",
    \"content\": \"User enjoys weekend hiking in mountain terrain\",
    \"importance_score\": 0.8,
    \"confidence\": 0.9,
    \"authority_level\": 2,
    \"payload\": {\"source\": \"conversation\", \"tags\": [\"outdoor\", \"fitness\"]}
  }"

# Get a specific memory by ID
curl http://localhost:8100/api/v1/memories/$MEMORY_ID

# List memories (with optional filters)
curl "http://localhost:8100/api/v1/memories?user_id=$USER_ID&memory_type=semantic&status=active&limit=50"

# Update a memory's status (archive, deprecate, etc.)
curl -s -X PATCH http://localhost:8100/api/v1/memories/$MEMORY_ID/status \
  -H "Content-Type: application/json" \
  -d '{"status": "archived"}'

# Get version history for a memory
curl http://localhost:8100/api/v1/memories/$MEMORY_ID/versions

# Get memory links (graph edges)
curl http://localhost:8100/api/v1/memories/$MEMORY_ID/links
```

### 3.8 Memory Links

```bash
# Create a typed link between two memories
curl -s -X POST http://localhost:8100/api/v1/memory-links \
  -H "Content-Type: application/json" \
  -d "{
    \"source_memory_id\": \"$MEMORY_A\",
    \"target_memory_id\": \"$MEMORY_B\",
    \"link_type\": \"supports\",
    \"weight\": 0.85,
    \"description\": \"Both memories relate to outdoor fitness preferences\"
  }"
```

**Link types**: `supports`, `contradicts`, `derived_from`, `supersedes`, `related_to`, `causal`, `temporal`.

### 3.9 Tasks

```bash
# Create a task
curl -s -X POST http://localhost:8100/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"title\": \"Summarize user preferences\",
    \"description\": \"Generate a preference profile from memories\",
    \"priority\": 2
  }"

# Transition task state
curl -s -X PATCH http://localhost:8100/api/v1/tasks/$TASK_ID/transition \
  -H "Content-Type: application/json" \
  -d '{"new_status": "in_progress"}'

# Valid state transitions:
#   pending       → in_progress, cancelled
#   in_progress   → completed, failed, paused, cancelled
#   paused        → in_progress, cancelled
#   failed        → pending (retry)

# List tasks
curl "http://localhost:8100/api/v1/tasks?user_id=$USER_ID&status=pending"
```

### 3.10 Artifacts

```bash
# Register artifact metadata
curl -s -X POST http://localhost:8100/api/v1/artifacts \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"memory_id\": \"$MEMORY_ID\",
    \"artifact_type\": \"file\",
    \"name\": \"preferences_export.json\",
    \"uri\": \"s3://my-bucket/exports/prefs.json\",
    \"size_bytes\": 4096
  }"

# Get artifact
curl http://localhost:8100/api/v1/artifacts/$ARTIFACT_ID
```

---

## 4. Python Embedded Client

The `agentmemodb` pip package runs entirely locally with SQLite — no server required.

### Installation

```bash
pip install agentmemodb                    # core (SQLite + hash-based embeddings)
pip install agentmemodb[openai]            # + real OpenAI embeddings
pip install agentmemodb[huggingface]       # + sentence-transformers (local)
pip install agentmemodb[all]               # everything
```

### Basic Usage

```python
import agentmemodb

# Open (or create) a local store
db = agentmemodb.Client()                           # saves to ./agentmemodb_data/
db = agentmemodb.Client(path="./my_app_memory")     # custom directory
db = agentmemodb.Client(path=":memory:")            # in-memory (tests only)

# Store memories
db.upsert("alice", "pref:language", "Alice prefers Python", memory_type="semantic")
db.upsert("alice", "pref:editor",   "Alice uses VS Code",   memory_type="semantic")
db.upsert("alice", "hobby:hiking",  "Alice enjoys hiking",  memory_type="semantic",
          importance=0.8, confidence=0.95)

# Semantic search
results = db.search("alice", "What does the user like to do?", top_k=5)
for r in results:
    print(f"  [{r.score:.3f}] {r.key}: {r.content}")

# Get by key
mem = db.get("alice", "pref:language")
print(mem.content, mem.version, mem.created_at)

# Get by UUID
mem = db.get_by_id("some-uuid-string")

# List with filters
all_mems = db.list("alice")
semantic  = db.list("alice", memory_type="semantic")
active    = db.list("alice", status="active", limit=20, offset=0)

# Count
total = db.count("alice")
active_count = db.count("alice", status="active")

# Delete
deleted = db.delete("alice", "pref:editor")   # returns True if existed

# Always close to flush the SQLite WAL
db.close()
```

### Using a Context Manager

```python
with agentmemodb.Client() as db:
    db.upsert("bob", "skill:python", "Expert in Python")
    results = db.search("bob", "programming skills")
```

### Real Embeddings — OpenAI

```python
import agentmemodb

db = agentmemodb.Client(
    embedding_fn=agentmemodb.OpenAIEmbedding(api_key="sk-...")
)
db.upsert("alice", "note:1", "I enjoy outdoor activities like hiking and cycling")
results = db.search("alice", "exercise and nature")   # real semantic search
```

### Real Embeddings — HuggingFace (Fully Local)

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")
embedding_fn = lambda text: model.encode(text).tolist()

db = agentmemodb.Client(embedding_fn=embedding_fn)
```

### PII Masking in Embedded Mode

```python
db = agentmemodb.Client(mask_pii=True)
db.upsert("u1", "contact", "Email me at alice@example.com or call 555-123-4567")
# Stored as: "Email me at [EMAIL] or call [PHONE]"

mem = db.get("u1", "contact")
print(mem.content)  # "Email me at [EMAIL] or call [PHONE]"
```

---

## 5. Python HTTP Client

Connects to a running AgentMemoryDB server. **Same API surface** as the embedded client — swap with zero code changes.

```python
import agentmemodb

# Connect to server (auth optional)
db = agentmemodb.HttpClient("http://localhost:8100")
db = agentmemodb.HttpClient("http://localhost:8100", api_key="amdb_...")

# All embedded client methods work identically
db.upsert("alice", "pref:lang", "Alice prefers Python")
results = db.search("alice", "programming language")
mem = db.get("alice", "pref:lang")
db.delete("alice", "pref:lang")
db.close()
```

### Async Server SDK (advanced)

For async FastAPI / LangGraph integration, use the internal async SDK:

```python
from app.sdk.client import AgentMemoryDBClient

async with AgentMemoryDBClient(
    base_url="http://localhost:8100",
    api_key="amdb_...",
) as client:
    memory  = await client.upsert_memory(
        user_id=user_id,
        memory_key="pref:lang",
        memory_type="semantic",
        content="User prefers Python",
    )
    results = await client.search_memories(user_id=user_id, query_text="language?")
    graph   = await client.expand_graph(memory["id"], max_hops=2)
    batch   = await client.bulk_upsert([item1, item2, item3])
```

---

## 6. TypeScript SDK

Located in `sdks/typescript/`. Provides a typed client for the REST API plus a real-time WebSocket helper.

### Installation

```bash
cd sdks/typescript
npm install
npm run build
```

Or when published:
```bash
npm install @agentmemorydb/sdk
```

### Basic Usage

```typescript
import { AgentMemoryDB } from '@agentmemorydb/sdk';

const db = new AgentMemoryDB({
  baseUrl: 'http://localhost:8100',
  apiKey: 'amdb_...',          // optional
});

// Create / update a memory
const memory = await db.memories.upsert({
  userId: 'alice',
  memoryKey: 'pref:language',
  memoryType: 'semantic',
  content: 'Alice prefers TypeScript',
});

// Hybrid search
const results = await db.memories.search({
  userId: 'alice',
  queryText: 'What programming language?',
  topK: 5,
});
results.results.forEach(r => {
  console.log(`[${r.score?.final_score.toFixed(3)}] ${r.memory.memory_key}: ${r.memory.content}`);
});

// Get / list
const mem  = await db.memories.get(memory.id);
const list = await db.memories.list({ userId: 'alice', memoryType: 'semantic' });
```

### Real-Time Events (WebSocket)

```typescript
// Subscribe to events for a user channel
const ws = db.realtime(['user:alice-uuid-here']);

ws.on('memory.created', (data) => {
  console.log('New memory created:', data.memory_key, data.content);
});

ws.on('memory.updated', (data) => {
  console.log('Memory updated:', data.memory_key);
});

ws.on('memory.status_changed', (data) => {
  console.log('Status changed to:', data.status);
});

// Unsubscribe
ws.close();
```

### Memory Graph (TypeScript)

```typescript
// BFS expand from a memory
const graph = await db.graph.expand(memoryId, { maxHops: 2 });
graph.nodes.forEach(n => console.log(n.memory_key, n.content));
graph.edges.forEach(e => console.log(e.link_type, e.weight));

// Shortest path between two memories
const path = await db.graph.shortestPath(memoryA, memoryB);
console.log('Path length:', path.path.length);
```

---

## 7. MemoryManager — Short-Term & Long-Term

`MemoryManager` combines a conversation buffer (short-term) with a persistent knowledge store (long-term) in the pip package.

### Setup

```python
from agentmemodb import MemoryManager

# Basic (hash embeddings, SQLite in ./agentmemodb_data/)
mgr = MemoryManager("alice")

# With real embeddings
from agentmemodb import OpenAIEmbedding
mgr = MemoryManager("alice", embedding_fn=OpenAIEmbedding(api_key="sk-..."))

# Context manager (auto-close)
with MemoryManager("alice") as mgr:
    ...
```

### Short-Term Memory (Conversation Buffer)

```python
# Build a conversation
mgr.short_term.add_system("You are a helpful coding assistant.")
mgr.short_term.add_user("How do I read a CSV file in Python?")
mgr.short_term.add_assistant("You can use pandas: `pd.read_csv('file.csv')`")
mgr.short_term.add_user("What about without pandas?")
mgr.short_term.add_assistant("Use the built-in `csv` module.")
mgr.short_term.add_tool("csv module docs loaded.")

# Retrieve messages
all_msgs = mgr.short_term.get_messages()                    # all messages
last_4   = mgr.short_term.get_last(4)                       # last 4
user_msgs = mgr.short_term.get_messages(roles=["user"])     # filter by role

# Export for LLM API call
openai_msgs = mgr.short_term.to_list()   # [{"role": "user", "content": "..."}]
text_block  = mgr.short_term.to_string() # "user: ...\nassistant: ...\n"

# Thread management
count = mgr.short_term.count()
mgr.short_term.clear()                   # clear current thread
mgr.new_thread("session-2")              # start a fresh thread
```

### Long-Term Memory (Persistent Knowledge)

```python
# Store facts with metadata
mgr.long_term.remember("pref:language",  "Alice prefers Python",         importance=0.9,  confidence=0.95)
mgr.long_term.remember("skill:ml",       "Experienced with PyTorch",     importance=0.85, confidence=0.9)
mgr.long_term.remember("goal:deploy",    "Wants to deploy on Kubernetes", importance=0.7,  confidence=0.8)

# Semantic recall
results = mgr.long_term.recall("programming skills", top_k=5)
for r in results:
    print(f"  [{r.score:.3f}] {r.key}: {r.content}")

# Direct access
mem = mgr.long_term.get("pref:language")
mgr.long_term.forget("goal:deploy")

# Listing
all_mems = mgr.long_term.list_all()
count = mgr.long_term.count()
```

### Unified Context Window (for LLM calls)

```python
# Build a context window combining recent messages + relevant memories
ctx = mgr.get_context_window(
    query="How should I deploy my Python API?",
    n_messages=10,    # last 10 conversation turns
    n_memories=5,     # top-5 relevant long-term memories
)

# ctx contains:
#   ctx["messages"]           – list of recent messages (OpenAI format)
#   ctx["relevant_memories"]  – [{"key": ..., "content": ..., "score": ...}]
#   ctx["stats"]              – {"message_count": 10, "memory_count": 3}

# Pass to your LLM
response = openai.chat.completions.create(
    model="gpt-4o",
    messages=ctx["messages"],
    system="\n".join(m["content"] for m in ctx["relevant_memories"]),
)
```

### Promote Short-Term → Long-Term

```python
# After a conversation, promote insights to permanent knowledge
mgr.promote("insight:deploy", "Alice prefers Docker + Gunicorn for FastAPI deployment")

# Equivalent to:
mgr.long_term.remember("insight:deploy", "Alice prefers Docker + Gunicorn for FastAPI deployment")
```

### Full Example: LLM Chatbot with Persistent Memory

```python
from agentmemodb import MemoryManager

def chat_with_memory(user_id: str):
    with MemoryManager(user_id) as mgr:
        print("Chat started. Type 'quit' to exit.")
        while True:
            user_input = input("You: ").strip()
            if user_input.lower() == "quit":
                break

            # Add user message to short-term
            mgr.short_term.add_user(user_input)

            # Build context window
            ctx = mgr.get_context_window(user_input, n_messages=8, n_memories=3)

            # Construct system prompt with long-term context
            memory_context = "\n".join(
                f"- {m['key']}: {m['content']}"
                for m in ctx["relevant_memories"]
            )
            system = f"You are a helpful assistant.\n\nWhat you know about the user:\n{memory_context}"

            # Call your LLM here
            response = call_llm(system=system, messages=ctx["messages"])

            # Add assistant reply
            mgr.short_term.add_assistant(response)
            print(f"Assistant: {response}")

            # Extract and store any facts mentioned
            if "i prefer" in user_input.lower() or "i like" in user_input.lower():
                mgr.promote(f"pref:{len(mgr.long_term.list_all())}", user_input)

chat_with_memory("alice-123")
```

---

## 8. Event → Observation → Memory Pipeline

This three-stage pipeline transforms raw inputs into versioned, searchable knowledge.

```
User message / tool call / function result
              ↓
           EVENT (raw capture)
              ↓
        OBSERVATION (structured fact)
              ↓
           MEMORY (versioned + searchable)
```

### Complete Pipeline Example

```bash
export BASE="http://localhost:8100/api/v1"

# 1. Create user + run
USER=$(curl -s -X POST $BASE/users -H "Content-Type: application/json" \
  -d '{"display_name": "Bob"}' | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

RUN=$(curl -s -X POST $BASE/runs -H "Content-Type: application/json" \
  -d "{\"user_id\": \"$USER\"}" | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

# 2. Record the raw event
EVENT=$(curl -s -X POST $BASE/events -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER\",
    \"run_id\": \"$RUN\",
    \"event_type\": \"user_message\",
    \"content\": \"I've been using Rust for systems programming since 2022\"
  }" | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

# 3. Extract an observation from the event
OBS=$(curl -s -X POST $BASE/observations -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER\",
    \"source_event_id\": \"$EVENT\",
    \"observation_type\": \"preference\",
    \"content\": \"User prefers Rust for systems programming\",
    \"confidence\": 0.92
  }" | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

# 4. Promote to a versioned memory
curl -s -X POST $BASE/memories/upsert -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER\",
    \"memory_key\": \"skill:rust\",
    \"memory_type\": \"semantic\",
    \"content\": \"User has been using Rust for systems programming since 2022\",
    \"source_event_id\": \"$EVENT\",
    \"source_observation_id\": \"$OBS\",
    \"source_run_id\": \"$RUN\",
    \"importance_score\": 0.8,
    \"confidence\": 0.92
  }" | python -m json.tool
```

---

## 9. Hybrid Search — All Options

The search endpoint combines vector similarity, recency, importance, authority, and confidence into one ranked list.

### Basic Text Search

```bash
curl -s -X POST http://localhost:8100/api/v1/memories/search \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"query_text\": \"What does the user like to eat?\"
  }" | python -m json.tool
```

### Filtered Search

```bash
curl -s -X POST http://localhost:8100/api/v1/memories/search \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"query_text\": \"outdoor activities\",
    \"memory_types\": [\"semantic\", \"episodic\"],
    \"scopes\": [\"user\", \"global\"],
    \"status\": \"active\",
    \"top_k\": 20,
    \"min_confidence\": 0.7,
    \"min_importance\": 0.5
  }"
```

### Metadata Filter Search

```bash
curl -s -X POST http://localhost:8100/api/v1/memories/search \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"query_text\": \"sports\",
    \"metadata_filter\": {\"tags\": [\"fitness\"], \"verified\": true}
  }"
```

### Explain Mode (Score Breakdown)

```bash
curl -s -X POST http://localhost:8100/api/v1/memories/search \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"query_text\": \"programming language\",
    \"explain\": true,
    \"top_k\": 5
  }" | python -m json.tool

# Response includes per-result score breakdown:
# {
#   "results": [{
#     "memory": { "memory_key": "pref:language", ... },
#     "score": {
#       "vector_score": 0.921,
#       "recency_score": 0.87,
#       "importance_score": 0.80,
#       "authority_score": 0.75,
#       "confidence_score": 0.90,
#       "final_score": 0.874
#     }
#   }],
#   "total_candidates": 42,
#   "strategy": "vector+fulltext"
# }
```

### Pre-computed Embedding Search

```bash
# Supply your own embedding vector (skips server-side embedding)
curl -s -X POST http://localhost:8100/api/v1/memories/search \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"embedding\": [0.12, -0.04, 0.89, ...],
    \"top_k\": 10
  }"
```

### Python SDK Search

```python
from app.sdk.client import AgentMemoryDBClient

async with AgentMemoryDBClient("http://localhost:8100") as client:
    response = await client.search_memories(
        user_id=user_id,
        query_text="favorite outdoor activity",
        memory_types=["semantic"],
        top_k=5,
        explain=True,
        min_confidence=0.7,
    )
    for item in response["results"]:
        m = item["memory"]
        s = item["score"]
        print(f"[{s['final_score']:.3f}] {m['memory_key']}: {m['content']}")
```

---

## 10. Memory Graph — Links, BFS, Shortest Path

Build a knowledge graph by linking memories with typed directed edges.

### Create Links

```bash
# Semantic support link
curl -s -X POST http://localhost:8100/api/v1/memory-links \
  -H "Content-Type: application/json" \
  -d "{
    \"source_memory_id\": \"$MEMORY_A\",
    \"target_memory_id\": \"$MEMORY_B\",
    \"link_type\": \"supports\",
    \"weight\": 0.9
  }"

# Contradiction link (auto-created when is_contradiction=true on upsert)
curl -s -X POST http://localhost:8100/api/v1/memories/upsert \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"memory_key\": \"pref:language\",
    \"memory_type\": \"semantic\",
    \"content\": \"User now prefers Go over Python\",
    \"is_contradiction\": true
  }"
```

**All link types**: `supports`, `contradicts`, `derived_from`, `supersedes`, `related_to`, `causal`, `temporal`, `conflict`.

### BFS Graph Expansion

```bash
# Expand outward from a memory node (BFS, up to 2 hops)
curl "http://localhost:8100/api/v1/graph/expand/$MEMORY_ID?max_hops=2&link_types=supports,related_to"

# Response:
# {
#   "root": { memory object },
#   "nodes": [ { memory object }, ... ],
#   "edges": [ { source_id, target_id, link_type, weight }, ... ],
#   "hop_counts": { "memory-uuid": 1, "memory-uuid-2": 2 }
# }
```

### Shortest Path

```bash
curl -s -X POST http://localhost:8100/api/v1/graph/shortest-path \
  -H "Content-Type: application/json" \
  -d "{
    \"source_id\": \"$MEMORY_A\",
    \"target_id\": \"$MEMORY_B\",
    \"max_depth\": 5
  }"

# Response:
# {
#   "path": [ memory_a, intermediate_node, memory_b ],
#   "edges": [ { link_type, weight }, ... ],
#   "length": 2
# }
```

### Python Graph Traversal

```python
from app.sdk.client import AgentMemoryDBClient

async with AgentMemoryDBClient("http://localhost:8100") as client:
    # BFS expand
    graph = await client.expand_graph(seed_memory_id, max_hops=3)
    print(f"Found {len(graph['nodes'])} related memories")
    for node in graph["nodes"]:
        print(f"  Hop {graph['hop_counts'][node['id']]}: {node['memory_key']}")

    # Shortest path
    path = await client.graph_shortest_path(memory_a_id, memory_b_id)
    for mem in path["path"]:
        print(f"  → {mem['memory_key']}")
```

---

## 11. Memory Versioning & Deduplication

Every upsert that changes the content creates a new version. Duplicate content is silently ignored.

### How It Works

- **SHA-256 content hash** is computed on every upsert.
- If the hash matches the current version, **no new version is created** (silent no-op).
- If the hash differs, the old content is archived in `memory_versions` and the canonical record is updated.
- The `version` counter increments on each real update.

### View Version History

```bash
# Get all versions for a memory
curl http://localhost:8100/api/v1/memories/$MEMORY_ID/versions

# Response: list of MemoryVersionResponse objects
# [{
#   "id": "...",
#   "memory_id": "...",
#   "version": 1,
#   "content": "Alice prefers Python",
#   "content_hash": "sha256:abc...",
#   "confidence": 0.9,
#   "superseded_at": "2025-03-14T10:00:00Z"
# }, ...]
```

### Trigger a Version Update

```bash
# Update content → creates version 2
curl -s -X POST http://localhost:8100/api/v1/memories/upsert \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"memory_key\": \"pref:language\",
    \"memory_type\": \"semantic\",
    \"content\": \"Alice now strongly prefers Python and Rust\"
  }"
# version field goes from 1 → 2
```

### Deduplication (exact or near-duplicate)

```bash
# Find duplicate memories
curl "http://localhost:8100/api/v1/consolidation/duplicates?user_id=$USER_ID"

# Merge two memories into one canonical record
curl -s -X POST http://localhost:8100/api/v1/consolidation/merge \
  -H "Content-Type: application/json" \
  -d "{
    \"primary_id\": \"$MEMORY_A\",
    \"duplicate_id\": \"$MEMORY_B\",
    \"merged_content\": \"Alice strongly prefers Python and has used Rust since 2022\"
  }"
```

---

## 12. Task State Machine

Tasks have a formal lifecycle. The API enforces valid state transitions.

### State Diagram

```
        ┌─────────────┐
        │   pending   │
        └──────┬──────┘
               │ start
       ┌───────▼───────┐
       │  in_progress  │◄──── resume ────┐
       └───┬───────────┘                 │
    done   │   fail   pause   cancel     │
           ▼     ▼       │       ▼       │
       completed  failed paused cancelled│
                           └─────────────┘
```

### Create and Advance a Task

```bash
# Create
TASK=$(curl -s -X POST http://localhost:8100/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"title\": \"Generate weekly summary\",
    \"priority\": 1
  }" | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Start
curl -s -X PATCH http://localhost:8100/api/v1/tasks/$TASK/transition \
  -H "Content-Type: application/json" \
  -d '{"new_status": "in_progress"}'

# Complete
curl -s -X PATCH http://localhost:8100/api/v1/tasks/$TASK/transition \
  -H "Content-Type: application/json" \
  -d '{"new_status": "completed"}'

# Or fail + retry
curl -s -X PATCH http://localhost:8100/api/v1/tasks/$TASK/transition \
  -H "Content-Type: application/json" \
  -d '{"new_status": "failed", "error_message": "LLM timeout"}'

curl -s -X PATCH http://localhost:8100/api/v1/tasks/$TASK/transition \
  -H "Content-Type: application/json" \
  -d '{"new_status": "pending"}'    # retry from failed
```

---

## 13. MCP Server — JSON-RPC Examples

The Model Context Protocol server exposes 7 tools callable by any MCP-compatible AI client (Claude Desktop, Cursor, etc.).

### Transport Options

**HTTP + SSE** (default, for web-based clients):
```
POST http://localhost:8100/api/v1/mcp/message
GET  http://localhost:8100/api/v1/mcp/sse        (SSE stream)
```

**stdio** (for CLI tools / local agents):
```bash
python -m app.mcp.transport --stdio
```

### List Available Tools

```bash
curl http://localhost:8100/api/v1/mcp/tools

# Returns 7 tools:
# store_memory, recall_memories, update_memory, get_memory_graph,
# create_task, transition_task, get_user_stats
```

### JSON-RPC Tool Calls

```bash
# Tool: store_memory
curl -s -X POST http://localhost:8100/api/v1/mcp/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "store_memory",
      "arguments": {
        "user_id": "alice-uuid",
        "memory_key": "pref:coffee",
        "content": "Alice drinks black coffee every morning",
        "memory_type": "semantic",
        "importance": 0.7
      }
    }
  }'

# Tool: recall_memories
curl -s -X POST http://localhost:8100/api/v1/mcp/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "recall_memories",
      "arguments": {
        "user_id": "alice-uuid",
        "query": "morning routine",
        "top_k": 5
      }
    }
  }'

# Tool: get_memory_graph
curl -s -X POST http://localhost:8100/api/v1/mcp/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "get_memory_graph",
      "arguments": {
        "memory_id": "'"$MEMORY_ID"'",
        "max_hops": 2
      }
    }
  }'

# Tool: create_task
curl -s -X POST http://localhost:8100/api/v1/mcp/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "create_task",
      "arguments": {
        "user_id": "alice-uuid",
        "title": "Summarize preferences",
        "priority": 2
      }
    }
  }'

# Tool: get_user_stats
curl -s -X POST http://localhost:8100/api/v1/mcp/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 5,
    "method": "tools/call",
    "params": {
      "name": "get_user_stats",
      "arguments": { "user_id": "alice-uuid" }
    }
  }'
```

### MCP in Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "agentmemorydb": {
      "command": "python",
      "args": ["-m", "app.mcp.transport", "--stdio"],
      "cwd": "/path/to/agentmemorydb"
    }
  }
}
```

---

## 14. WebSocket — Real-Time Events

Subscribe to live memory events for one or more users/projects.

### Connect & Subscribe

```javascript
// Browser WebSocket
const ws = new WebSocket('ws://localhost:8100/ws');

ws.onopen = () => {
  // Subscribe to a user channel
  ws.send(JSON.stringify({
    type: 'subscribe',
    channels: ['user:alice-uuid-here']
  }));

  // Subscribe to multiple channels
  ws.send(JSON.stringify({
    type: 'subscribe',
    channels: ['user:alice-uuid', 'project:proj-uuid']
  }));
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  console.log('Event type:', msg.event_type);   // e.g. "memory.created"
  console.log('Channel:', msg.channel);
  console.log('Data:', msg.data);
};
```

### Event Types

| Event Type | Trigger |
|------------|---------|
| `memory.created` | New memory upserted |
| `memory.updated` | Existing memory content changed |
| `memory.status_changed` | Status changed (archived, deprecated, etc.) |
| `memory.linked` | A new link created |
| `task.status_changed` | Task state transition |

### In-Session Commands (via WebSocket)

```javascript
// Search without HTTP
ws.send(JSON.stringify({
  type: 'search',
  user_id: 'alice-uuid',
  query_text: 'morning routine',
  top_k: 5
}));

// Ping / keep-alive
ws.send(JSON.stringify({ type: 'ping' }));
```

### Python WebSocket Client

```python
import asyncio
import json
import websockets

async def listen():
    async with websockets.connect("ws://localhost:8100/ws") as ws:
        await ws.send(json.dumps({
            "type": "subscribe",
            "channels": ["user:alice-uuid"]
        }))
        async for message in ws:
            event = json.loads(message)
            print(f"[{event['event_type']}] {event['data'].get('memory_key', '')}")

asyncio.run(listen())
```

---

## 15. LangChain Integration

The pip package (`agentmemodb[langchain]`) provides drop-in LangChain components.

### Installation

```bash
pip install agentmemodb[langchain]
```

### Chat History (BaseChatMessageHistory)

```python
from agentmemodb.integrations.langchain import AgentMemoryDBChatHistory
from langchain_openai import ChatOpenAI
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory

# Persistent chat history backed by AgentMemoryDB
history = AgentMemoryDBChatHistory(user_id="alice")

# Use in a ConversationChain
memory = ConversationBufferMemory(
    chat_memory=history,
    return_messages=True
)
chain = ConversationChain(llm=ChatOpenAI(), memory=memory)

response = chain.predict(input="I love hiking in the Alps.")
response = chain.predict(input="What are my outdoor hobbies?")
# Remembers "hiking in the Alps" across calls, even after restart
```

### Retriever (BaseRetriever → Documents)

```python
from agentmemodb.integrations.langchain import AgentMemoryDBRetriever
from langchain.chains import RetrievalQA
from langchain_openai import ChatOpenAI

retriever = AgentMemoryDBRetriever(user_id="alice", top_k=5)
# Returns LangChain Document objects with:
#   doc.page_content = memory content
#   doc.metadata = {"key": "...", "score": 0.92, "memory_type": "semantic"}

qa_chain = RetrievalQA.from_chain_type(
    llm=ChatOpenAI(),
    retriever=retriever
)
answer = qa_chain.invoke("What programming language does Alice prefer?")
```

### Conversation Memory (History + Knowledge)

```python
from agentmemodb.integrations.langchain import AgentMemoryDBConversationMemory

memory = AgentMemoryDBConversationMemory(user_id="alice", top_k=3)

# load_memory_variables returns:
# {
#   "history": "Human: ...\nAI: ...",
#   "relevant_context": "- pref:language: Alice prefers Python\n..."
# }
vars = memory.load_memory_variables({"input": "best language for ML?"})
```

### Agent Memory Tool

```python
from agentmemodb.integrations.langchain import create_memory_tool
from langchain.agents import AgentExecutor, create_openai_functions_agent

memory_tool = create_memory_tool(user_id="alice")
# Tool accepts JSON: {"action": "store", "key": "...", "content": "..."}
#                or  {"action": "recall", "query": "..."}

# Add to any LangChain agent
tools = [memory_tool, ...other_tools...]
agent = create_openai_functions_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools)
```

---

## 16. LangGraph Integration

Full LangGraph support — store, checkpoint persistence, and pre-built memory nodes.

### Installation

```bash
pip install agentmemodb[langgraph]
```

### LangGraph Store

```python
from agentmemodb.integrations.langgraph import AgentMemoryDBStore

store = AgentMemoryDBStore(user_id="alice")

# Put / get / delete
await store.put("alice", "pref:color", "Alice likes blue")
result = await store.get("alice", "pref:color")

# Semantic search
results = await store.search("alice", "colour preferences", top_k=5)
for item in results:
    print(item["key"], item["content"], item["score"])

# As plain text (for injection into prompts)
context = await store.search_as_text("alice", "food preferences")
print(context)  # "- pref:food: Alice is vegetarian\n- pref:cuisine: Loves Thai food"

# List / count / delete
all_items = await store.list("alice")
count = await store.count("alice")
await store.delete("alice", "pref:color")
```

### Checkpoint Persistence (Saver)

```python
from agentmemodb.integrations.langgraph import AgentMemoryDBSaver
from langgraph.graph import StateGraph

saver = AgentMemoryDBSaver(user_id="alice")

graph = StateGraph(MyState)
# ... define nodes and edges ...
app = graph.compile(checkpointer=saver)

# Run with thread persistence
config = {"configurable": {"thread_id": "session-001"}}
result = await app.ainvoke({"input": "Hello"}, config=config)

# Resume same thread
result2 = await app.ainvoke({"input": "Continue"}, config=config)

# Time-travel: list checkpoints
checkpoints = await saver.list_checkpoints("session-001")
# Restore from a specific checkpoint
old_result = await saver.get_tuple("session-001", checkpoint_id=checkpoints[-2].id)
```

### Pre-built Memory Nodes

```python
from agentmemodb.integrations.langgraph import create_memory_node, create_save_memory_node
from langgraph.graph import StateGraph, END
from typing import TypedDict

class AgentState(TypedDict):
    input: str
    context: str
    output: str

# Recall node: reads state["input"] → injects relevant memories into state["context"]
recall_node = create_memory_node(
    user_id="alice",
    input_key="input",
    context_key="context",
    top_k=5
)

# Save node: reads state["output"] → saves to long-term memory
save_node = create_save_memory_node(
    user_id="alice",
    content_key="output",
    memory_key_prefix="session_output"
)

# Build graph with memory
graph = StateGraph(AgentState)
graph.add_node("recall",   recall_node)
graph.add_node("respond",  respond_node)    # your LLM node
graph.add_node("remember", save_node)

graph.set_entry_point("recall")
graph.add_edge("recall",   "respond")
graph.add_edge("respond",  "remember")
graph.add_edge("remember", END)

agent = graph.compile()
result = await agent.ainvoke({"input": "What's my preferred language?"})
```

### Full Agent with Server-Side Store

```python
from app.adapters.langgraph_store import AgentMemoryDBStore

# Connect to the running server (async)
store = AgentMemoryDBStore(base_url="http://localhost:8100/api/v1")

await store.put(user_id, "pref:editor", "User uses Neovim")
results = await store.search(user_id, "editor preferences", top_k=3)
```

---

## 17. Bulk Operations

Process up to 100 upserts or 20 searches in a single request.

### Bulk Upsert (≤ 100 items)

```bash
curl -s -X POST http://localhost:8100/api/v1/bulk/upsert \
  -H "Content-Type: application/json" \
  -d "{
    \"items\": [
      {
        \"user_id\": \"$USER_ID\",
        \"memory_key\": \"pref:language\",
        \"memory_type\": \"semantic\",
        \"content\": \"Prefers Python\"
      },
      {
        \"user_id\": \"$USER_ID\",
        \"memory_key\": \"pref:editor\",
        \"memory_type\": \"semantic\",
        \"content\": \"Uses VS Code\"
      },
      {
        \"user_id\": \"$USER_ID\",
        \"memory_key\": \"pref:os\",
        \"memory_type\": \"semantic\",
        \"content\": \"Runs Windows 11\"
      }
    ]
  }"
```

### Bulk Search (≤ 20 queries)

```bash
curl -s -X POST http://localhost:8100/api/v1/bulk/search \
  -H "Content-Type: application/json" \
  -d "{
    \"queries\": [
      {\"user_id\": \"$USER_ID\", \"query_text\": \"programming language\", \"top_k\": 3},
      {\"user_id\": \"$USER_ID\", \"query_text\": \"development tools\", \"top_k\": 3},
      {\"user_id\": \"$USER_ID\", \"query_text\": \"operating system\", \"top_k\": 3}
    ]
  }"
# Returns an array of search responses, one per query
```

### Python Bulk Upsert

```python
from app.sdk.client import AgentMemoryDBClient

async with AgentMemoryDBClient("http://localhost:8100") as client:
    items = [
        {"user_id": user_id, "memory_key": f"fact:{i}", "memory_type": "semantic",
         "content": f"Fact number {i}"}
        for i in range(50)
    ]
    result = await client.bulk_upsert(items)
    print(f"Upserted {result['created']} new, updated {result['updated']} existing")
```

---

## 18. Import & Export

### Export All Memories

```bash
# Export as JSON (all memories for a user)
curl "http://localhost:8100/api/v1/data/export?user_id=$USER_ID" \
  -o memories_backup.json

# Export with filters
curl "http://localhost:8100/api/v1/data/export?user_id=$USER_ID&memory_type=semantic&status=active" \
  -o semantic_memories.json
```

### Import from JSON

```bash
# Import (upserts existing keys, inserts new ones)
curl -s -X POST http://localhost:8100/api/v1/data/import \
  -H "Content-Type: application/json" \
  -d @memories_backup.json
```

### CLI Export / Import

```bash
# Export
agentmemodb export --user-id $USER_ID -o alice_memories.json

# Import
agentmemodb import alice_memories.json

# Export filtered
agentmemodb export --user-id $USER_ID --type semantic -o semantic.json
```

---

## 19. Memory Consolidation

Automatically find and merge near-duplicate memories to keep the knowledge base clean.

### Manual Consolidation

```bash
# Step 1: find duplicates
curl "http://localhost:8100/api/v1/consolidation/duplicates?user_id=$USER_ID&threshold=0.95"
# Returns pairs of memories with similarity above the threshold

# Step 2: merge two memories
curl -s -X POST http://localhost:8100/api/v1/consolidation/merge \
  -H "Content-Type: application/json" \
  -d "{
    \"primary_id\": \"$MEMORY_KEEP\",
    \"duplicate_id\": \"$MEMORY_DISCARD\",
    \"merged_content\": \"Combined and deduplicated content here\"
  }"
```

### Auto-Consolidation

```bash
# Run full auto-consolidation for a user (exact + near-dup detection + merge)
curl -s -X POST http://localhost:8100/api/v1/consolidation/auto \
  -H "Content-Type: application/json" \
  -d "{\"user_id\": \"$USER_ID\"}"

# Returns:
# {
#   "duplicates_found": 3,
#   "merged": 3,
#   "skipped": 0
# }
```

### CLI

```bash
agentmemodb consolidate                      # auto-consolidate all users
agentmemodb consolidate --user-id $USER_ID   # single user
```

### Scheduled Auto-Consolidation

Consolidation runs automatically every hour by default. Configure with:
```env
SCHEDULER_ENABLE_CONSOLIDATION=true
SCHEDULER_CONSOLIDATION_INTERVAL=3600  # seconds
```

---

## 20. PII Data Masking

Automatically detect and redact PII from memory content before storage.

### Enable Masking

```env
# .env or docker-compose environment
ENABLE_DATA_MASKING=true
MASKING_PATTERNS=email,phone,ssn,credit_card,ip_address,url,name
MASKING_LOG_DETECTIONS=true
```

### Built-in Patterns

| Pattern Name | Matches | Replacement |
|-------------|---------|-------------|
| `email` | `alice@example.com` | `[EMAIL]` |
| `phone` | `555-123-4567`, `+1 (555) 123-4567` | `[PHONE]` |
| `ssn` | `123-45-6789` | `[SSN]` |
| `credit_card` | `4111-1111-1111-1111` | `[CREDIT_CARD]` |
| `ip_address` | `192.168.1.1`, `2001:db8::1` | `[IP_ADDRESS]` |
| `url` | `https://example.com/path` | `[URL]` |
| `name` | Proper names (heuristic) | `[NAME]` |

### Test PII Detection (Dry Run)

```bash
curl -s -X POST http://localhost:8100/api/v1/masking/test \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Contact Alice at alice@example.com or 555-123-4567. SSN: 123-45-6789"
  }'

# Response:
# {
#   "original": "Contact Alice at alice@example.com or 555-123-4567. SSN: 123-45-6789",
#   "masked": "Contact Alice at [EMAIL] or [PHONE]. SSN: [SSN]",
#   "detections": [
#     {"pattern": "email", "value": "alice@example.com", "start": 17, "end": 34},
#     {"pattern": "phone", "value": "555-123-4567", "start": 38, "end": 50},
#     {"pattern": "ssn",   "value": "123-45-6789",  "start": 57, "end": 68}
#   ]
# }
```

### View Masking Audit Logs

```bash
# Query the masking audit trail
curl "http://localhost:8100/api/v1/masking/logs?user_id=$USER_ID&limit=50"

# Aggregate stats
curl http://localhost:8100/api/v1/masking/stats

# Current masking configuration
curl http://localhost:8100/api/v1/masking/config
```

### Custom PII Patterns

```env
MASKING_CUSTOM_PATTERNS=[{"name":"employee_id","regex":"EMP-\\d{6}","token":"[EMP_ID]"},{"name":"project_code","regex":"PROJ-[A-Z]{4}-\\d{4}","token":"[PROJECT]"}]
```

### Python Standalone Masking

```python
from agentmemodb.masking import PIIMaskingEngine

engine = PIIMaskingEngine(patterns=["email", "phone", "ssn"])
masked, detections = engine.mask("Call me at 555-1234 or email@example.com")
print(masked)       # "Call me at [PHONE] or [EMAIL]"
print(detections)   # [Detection(pattern="phone", ...), Detection(pattern="email", ...)]

# Dict masking (masks all string values recursively)
data = {"user": "alice", "contact": "alice@co.com", "notes": {"phone": "555-0000"}}
masked_data = engine.mask_dict(data)
```

---

## 21. Authentication & API Keys

### Enable Authentication

```env
REQUIRE_AUTH=true
```

When enabled, all API requests must include `X-API-Key: amdb_<token>`.

### Create an API Key

```bash
curl -s -X POST http://localhost:8100/api/v1/api-keys \
  -H "Content-Type: application/json" \
  -d '{
    "name": "production-agent",
    "scopes": ["read", "write"],
    "expires_in_days": 90
  }'

# Response:
# {
#   "id": "...",
#   "name": "production-agent",
#   "key": "amdb_xxxxxxxxxxxxxxxxxxxxxxxxxxx",   ← store this securely, shown ONCE
#   "prefix": "amdb_xxxx",
#   "scopes": ["read", "write"],
#   "expires_at": "2025-06-14T00:00:00Z"
# }
```

### Use the API Key

```bash
# All subsequent requests
curl http://localhost:8100/api/v1/memories/$MEMORY_ID \
  -H "X-API-Key: amdb_your_key_here"
```

### Revoke a Key

```bash
curl -s -X DELETE http://localhost:8100/api/v1/api-keys/$KEY_ID
```

### Available Scopes

| Scope | Permissions |
|-------|-------------|
| `read` | GET endpoints only |
| `write` | POST/PATCH/DELETE |
| `admin` | All endpoints + management |

### Implementation Details

- Keys are SHA-256 hashed before storage (raw key never stored)
- Keys have a `amdb_` prefix for easy identification in logs
- Expiration enforced on every request
- Failed auth returns `401 Unauthorized`

---

## 22. Row Level Security

RLS enforces database-level tenant isolation — no application code required.

### Enable RLS

```env
ENABLE_RLS=true
```

### How It Works

Three database roles are created:

| Role | Access |
|------|--------|
| `agentmemodb_admin` | Full access to all rows |
| `agentmemodb_agent` | Read/write own rows only (enforced by `user_id` policy) |
| `agentmemodb_readonly` | Read own rows only |

The application sets a tenant context at the start of each request:
```sql
SET LOCAL agentmemodb.current_user_id = '<user_uuid>';
```

PostgreSQL RLS policies then automatically filter all queries so that agents can only see their own data.

### Apply RLS Migrations

```bash
# Run the RLS migration
docker compose exec app python -m alembic upgrade head

# Or manually
psql $DATABASE_URL -f migrations/versions/enable_rls.sql
```

---

## 23. Webhooks

Register HTTP endpoints to receive real-time events as they happen.

### Register a Webhook

```bash
curl -s -X POST http://localhost:8100/api/v1/webhooks \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-server.com/webhooks/memory-events",
    "events": ["memory.created", "memory.updated", "task.status_changed"],
    "secret": "your-signing-secret-here",
    "description": "Production event handler"
  }'
```

### Verify Webhook Signatures (Python)

```python
import hmac
import hashlib

def verify_webhook(payload: bytes, signature: str, secret: str) -> bool:
    """Verify the HMAC-SHA256 webhook signature."""
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)

# In your FastAPI / Flask handler:
@app.post("/webhooks/memory-events")
async def handle_webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get("X-AgentMemoryDB-Signature", "")
    if not verify_webhook(payload, signature, "your-signing-secret-here"):
        raise HTTPException(status_code=401)
    event = await request.json()
    print(f"Event: {event['event_type']}, Memory: {event['data'].get('memory_key')}")
    return {"ok": True}
```

### Webhook Payload Format

```json
{
  "event_type": "memory.created",
  "timestamp": "2025-03-14T10:30:00Z",
  "webhook_id": "wh-uuid",
  "data": {
    "id": "memory-uuid",
    "user_id": "user-uuid",
    "memory_key": "pref:language",
    "content": "User prefers Python",
    "memory_type": "semantic",
    "version": 1
  }
}
```

### Manage Webhooks

```bash
# List all webhooks
curl http://localhost:8100/api/v1/webhooks

# Delete a webhook
curl -s -X DELETE http://localhost:8100/api/v1/webhooks/$WEBHOOK_ID
```

### Retry Policy

Failed deliveries (non-2xx response or timeout) are retried with exponential backoff:
- Attempt 1: immediate
- Attempt 2: 30s
- Attempt 3: 5 minutes
- Attempt 4: 30 minutes
- After 4 failures: marked as `failed`, no further retries

---

## 24. Scheduled Maintenance

Five background jobs run automatically to keep the memory store healthy.

### Jobs Overview

| Job | Interval | Description |
|-----|----------|-------------|
| **consolidation** | 1 hour | Find + merge near-duplicate memories |
| **archive** | 2 hours | Archive memories older than threshold (default 90 days) |
| **recency** | 30 minutes | Refresh recency decay scores |
| **cleanup** | 1 hour | Delete cancelled tasks, purge expired memories |
| **prune** | 24 hours | Prune old access logs and masking logs |

### Monitor Scheduler Status

```bash
curl http://localhost:8100/api/v1/scheduler/status

# Response:
# {
#   "status": "running",
#   "jobs": [
#     {"name": "consolidation", "next_run": "2025-03-14T11:00:00Z", "last_run": "2025-03-14T10:00:00Z"},
#     {"name": "archive",       "next_run": "2025-03-14T12:00:00Z", "last_run": "2025-03-14T10:00:00Z"},
#     ...
#   ]
# }
```

### Manually Trigger a Job

```bash
# Trigger consolidation now
curl -s -X POST http://localhost:8100/api/v1/scheduler/jobs/consolidation/run

# Trigger archive now
curl -s -X POST http://localhost:8100/api/v1/scheduler/jobs/archive/run

# Trigger recency refresh
curl -s -X POST http://localhost:8100/api/v1/scheduler/jobs/recency/run
```

### CLI Scheduler Commands

```bash
agentmemodb archive-stale --days 90      # archive memories older than 90 days
agentmemodb consolidate                  # run dedup + merge
agentmemodb recompute-recency            # refresh all recency scores
```

### Configure Intervals

```env
SCHEDULER_CONSOLIDATION_INTERVAL=3600   # seconds
SCHEDULER_ARCHIVE_INTERVAL=7200
SCHEDULER_RECENCY_INTERVAL=1800
SCHEDULER_CLEANUP_INTERVAL=3600
SCHEDULER_PRUNE_INTERVAL=86400
SCHEDULER_STALE_THRESHOLD_DAYS=90
SCHEDULER_ACCESS_LOG_RETENTION_DAYS=90

# Enable/disable individual jobs
SCHEDULER_ENABLE_CONSOLIDATION=true
SCHEDULER_ENABLE_ARCHIVE=true
SCHEDULER_ENABLE_RECENCY=true
SCHEDULER_ENABLE_CLEANUP=true
SCHEDULER_ENABLE_PRUNE=true
```

---

## 25. Observability

### Prometheus Metrics

```bash
# Scrape the metrics endpoint
curl http://localhost:8100/metrics

# Key metrics:
# agentmemodb_memories_created_total        — counter, labeled by memory_type, scope
# agentmemodb_memories_updated_total        — counter
# agentmemodb_searches_total                — counter, labeled by strategy
# agentmemodb_search_latency_seconds        — histogram
# agentmemodb_active_memories_count         — gauge (per user sampled)
# agentmemodb_websocket_connections_active  — gauge
```

### Prometheus Scrape Config

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'agentmemorydb'
    static_configs:
      - targets: ['localhost:8100']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

### Structured Logging

All requests are logged as JSON with:
- `request_id` — unique UUID per request (also in `X-Request-ID` response header)
- `method`, `path`, `status_code`, `duration_ms`
- `user_id` (when present)

```bash
# View structured logs from Docker
docker compose logs -f app | python -c "
import sys, json
for line in sys.stdin:
    try:
        log = json.loads(line)
        print(f'[{log[\"level\"]}] {log[\"message\"]} ({log.get(\"duration_ms\", \"\")}ms)')
    except:
        print(line, end='')
"
```

### Request Tracing

Each request gets a unique ID. Trace a full request chain:
```bash
curl -v http://localhost:8100/api/v1/memories/search \
  -H "Content-Type: application/json" \
  -d "{...}" 2>&1 | grep "X-Request-ID"
# X-Request-ID: req-7f3a2b1c-...
```

### Health Endpoints for Monitoring

```bash
# For load balancer health checks
curl http://localhost:8100/api/v1/health
# Returns 200 {"status": "ok"} when healthy

# For deep diagnostics
curl http://localhost:8100/api/v1/health/deep
# Returns 200 with DB connection, pgvector availability, and memory count
# Returns 503 if DB is unreachable
```

---

## 26. Access Tracking

Every time a memory is returned in a search result, its access count is incremented. This popularity signal feeds back into future search scores.

### How It Works

When `ENABLE_ACCESS_TRACKING=true`:
1. Every search response automatically records which memories were returned.
2. A background job counts accesses within the tracking window (default 168 hours = 7 days).
3. Memories with high recent access counts get an importance boost: `new_importance = old_importance + ACCESS_BOOST_FACTOR × access_count_in_window`.
4. This makes frequently-recalled memories rise in future rankings automatically.

### Configuration

```env
ENABLE_ACCESS_TRACKING=true
ACCESS_BOOST_FACTOR=0.05         # importance boost per access
ACCESS_BOOST_WINDOW_HOURS=168    # 7-day rolling window
```

### Manual Retrieval Log

```bash
# Explicitly log that a memory was used (for analytics)
curl -s -X POST http://localhost:8100/api/v1/retrieval-logs \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"memory_id\": \"$MEMORY_ID\",
    \"query_text\": \"outdoor activities\",
    \"run_id\": \"$RUN_ID\"
  }"
```

---

## 27. CLI Tool

The `agentmemodb` CLI is available after installing the pip package.

```bash
pip install agentmemodb
agentmemodb --help
```

### All Commands

```bash
# System
agentmemodb health                            # Health check (exits 0 if OK)
agentmemodb stats                             # Memory + user statistics

# Data management
agentmemodb export --user-id UUID -o out.json  # Export memories to JSON
agentmemodb import data.json                   # Import from JSON (upsert semantics)

# Maintenance
agentmemodb archive-stale --days 90            # Archive memories older than N days
agentmemodb consolidate                        # Run dedup + merge
agentmemodb recompute-recency                  # Refresh recency decay scores

# Database (requires DB access)
agentmemodb migrate                            # Run pending Alembic migrations
agentmemodb downgrade                          # Roll back last migration
agentmemodb shell                              # Open Python REPL with app context

# Configuration
agentmemodb config                             # Print current configuration
```

### Connect to a Remote Server

```bash
export AGENTMEMODB_URL=http://my-server:8100
export AGENTMEMODB_API_KEY=amdb_...

agentmemodb stats
agentmemodb export --user-id $USER_ID -o backup.json
```

---

## 28. Explorer UI

A built-in React web app for visually exploring memories, graph connections, events, and settings.

### Access

```
http://localhost:8100/explorer
```

### Pages

| Page | URL | Description |
|------|-----|-------------|
| **Dashboard** | `/explorer` | Memory count, recent activity, system stats |
| **Explorer** | `/explorer/search` | Full-text + semantic search, filters, memory detail panel |
| **Graph** | `/explorer/graph` | Interactive D3.js force-directed memory graph |
| **Events** | `/explorer/events` | Live WebSocket event stream with filters |
| **Settings** | `/explorer/settings` | Server URL, API key, embedding provider |

### Graph Visualization Tips

1. Open `/explorer/graph`.
2. Enter a starting memory ID or click any memory in the Explorer.
3. Use the slider to control max hops (1–5).
4. Hover nodes to see memory content; click to open detail panel.
5. Edge colors indicate link type (green = supports, red = contradicts, grey = related).

### Live Event Stream

1. Open `/explorer/events`.
2. Events appear in real-time as memories are created/updated.
3. Filter by event type or user channel using the sidebar filters.

---

## 29. Docker & Deployment

### Quick Start

```bash
# 1. Clone
git clone https://github.com/ioteverythin/agentmemorydb.git
cd agentmemorydb

# 2. Configure
cp .env.example .env
# Edit .env: set EMBEDDING_PROVIDER, OPENAI_API_KEY, etc.

# 3. Start
docker compose up -d

# 4. Check health
curl http://localhost:8100/api/v1/health
```

### Docker Compose Services

| Service | Port | Description |
|---------|------|-------------|
| `db` | 5432 | PostgreSQL 16 + pgvector |
| `app` | 8100 | Production API + Explorer UI |
| `app-dev` | 8101 | Dev server with hot-reload (profile: `dev`) |

### Custom Port (avoid conflicts)

```bash
DB_PORT=5433 docker compose up -d
```

### Production Configuration

```bash
# .env for production
ENVIRONMENT=production
LOG_LEVEL=WARNING
REQUIRE_AUTH=true
ENABLE_RLS=false         # enable after running RLS migration
EMBEDDING_PROVIDER=sentence-transformers
EMBEDDING_DIMENSION=384
ENABLE_DATA_MASKING=true
MASKING_PATTERNS=email,phone,ssn,credit_card
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/agentmemodb
```

### Build the Docker Image

```bash
# Standard build
docker build -t agentmemodb-app:latest .

# With sentence-transformers (adds ~4GB for PyTorch)
docker build \
  --build-arg INSTALL_SENTENCE_TRANSFORMERS=1 \
  -t agentmemodb-app:sentence-transformers \
  .
```

### Run Migrations

```bash
# Inside the container
docker compose exec app python -m alembic upgrade head

# Or via entrypoint
docker compose exec app /docker/entrypoint.sh migrate
```

### Entrypoint Commands

```bash
docker compose exec app /docker/entrypoint.sh serve        # production server
docker compose exec app /docker/entrypoint.sh serve-dev    # dev + hot-reload
docker compose exec app /docker/entrypoint.sh migrate      # run migrations
docker compose exec app /docker/entrypoint.sh downgrade    # rollback
docker compose exec app /docker/entrypoint.sh shell        # Python REPL
```

### Kubernetes Deployment

```yaml
# deployment.yaml (minimal example)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agentmemorydb
spec:
  replicas: 2
  selector:
    matchLabels: { app: agentmemorydb }
  template:
    spec:
      containers:
        - name: app
          image: agentmemodb-app:latest
          ports:
            - containerPort: 8100
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: agentmemorydb-secrets
                  key: database_url
            - name: EMBEDDING_PROVIDER
              value: "sentence-transformers"
            - name: REQUIRE_AUTH
              value: "true"
          livenessProbe:
            httpGet:
              path: /api/v1/health
              port: 8100
          readinessProbe:
            httpGet:
              path: /api/v1/health/deep
              port: 8100
```

---

## 30. Configuration Reference

All settings via environment variables or `.env` file. The `docker-compose.yml` passes these to the container.

### Application

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `AgentMemoryDB` | Application name (shown in logs + UI) |
| `ENVIRONMENT` | `development` | `development` or `production` |
| `LOG_LEVEL` | `INFO` | Python log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `ENABLE_DOCS` | `true` | Enable Swagger UI at `/docs` and ReDoc at `/redoc` |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Full async PostgreSQL URL |
| `DATABASE_ECHO` | `false` | Log all SQL to stdout (verbose, dev only) |

### Embeddings

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_PROVIDER` | `dummy` | `dummy` / `openai` / `cohere` / `sentence-transformers` / `ollama` |
| `EMBEDDING_DIMENSION` | `1536` | Must match the model output dimension |
| `VECTOR_INDEX_LISTS` | `100` | pgvector IVFFlat index lists parameter |
| `OPENAI_API_KEY` | — | Required for `openai` provider |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI model name |
| `COHERE_API_KEY` | — | Required for `cohere` provider |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `nomic-embed-text` | Ollama model name |

**Embedding provider dimensions:**

| Provider | Model | Dimension |
|----------|-------|-----------|
| `dummy` | hash-based | 1536 |
| `openai` | `text-embedding-3-small` | 1536 |
| `openai` | `text-embedding-3-large` | 3072 |
| `sentence-transformers` | `all-MiniLM-L6-v2` | 384 |
| `cohere` | `embed-english-v3.0` | 1024 |
| `ollama` | `nomic-embed-text` | 768 |

### Retrieval & Scoring

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_TOP_K` | `10` | Default number of search results |
| `SCORE_WEIGHT_VECTOR` | `0.45` | Vector similarity weight |
| `SCORE_WEIGHT_RECENCY` | `0.20` | Recency decay weight |
| `SCORE_WEIGHT_IMPORTANCE` | `0.15` | Importance score weight |
| `SCORE_WEIGHT_AUTHORITY` | `0.10` | Authority level weight |
| `SCORE_WEIGHT_CONFIDENCE` | `0.10` | Confidence weight |
| `ENABLE_FULLTEXT_SEARCH` | `true` | GIN-indexed tsvector full-text search |
| `FULLTEXT_WEIGHT` | `0.1` | Full-text contribution to hybrid score |

### Auth & Security

| Variable | Default | Description |
|----------|---------|-------------|
| `REQUIRE_AUTH` | `false` | Enforce `X-API-Key` on all requests |
| `ENABLE_RLS` | `false` | Enable PostgreSQL Row Level Security |

### Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_WEBHOOKS` | `true` | Enable webhook delivery |
| `ENABLE_METRICS` | `true` | Expose `/metrics` Prometheus endpoint |
| `ENABLE_ACCESS_TRACKING` | `true` | Track which memories are accessed |
| `ENABLE_WEBSOCKET` | `true` | Enable `/ws` WebSocket endpoint |
| `ENABLE_MCP` | `true` | Enable MCP JSON-RPC server |
| `ENABLE_EXPLORER` | `true` | Serve Explorer UI at `/explorer` |
| `ENABLE_SCHEDULER` | `true` | Run background maintenance jobs |

### Data Masking

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_DATA_MASKING` | `false` | Enable PII masking pipeline |
| `MASKING_PATTERNS` | `email,phone,ssn,credit_card,ip_address` | Comma-separated pattern names |
| `MASKING_LOG_DETECTIONS` | `true` | Audit log each masking action |
| `MASKING_CUSTOM_PATTERNS` | — | JSON array: `[{"name":"...","regex":"...","token":"..."}]` |

### Access Tracking

| Variable | Default | Description |
|----------|---------|-------------|
| `ACCESS_BOOST_FACTOR` | `0.05` | Importance boost per recent access |
| `ACCESS_BOOST_WINDOW_HOURS` | `168` | Rolling window for access counting (7 days) |

### Scheduler

| Variable | Default | Description |
|----------|---------|-------------|
| `SCHEDULER_CONSOLIDATION_INTERVAL` | `3600` | Seconds between consolidation runs |
| `SCHEDULER_ARCHIVE_INTERVAL` | `7200` | Seconds between archiving runs |
| `SCHEDULER_RECENCY_INTERVAL` | `1800` | Seconds between recency refreshes |
| `SCHEDULER_CLEANUP_INTERVAL` | `3600` | Seconds between cleanup runs |
| `SCHEDULER_PRUNE_INTERVAL` | `86400` | Seconds between log pruning |
| `SCHEDULER_STALE_THRESHOLD_DAYS` | `90` | Archive memories inactive for this many days |
| `SCHEDULER_ACCESS_LOG_RETENTION_DAYS` | `90` | Prune access logs older than this |

---

## Appendix A: Run the Agent Demo

The repository includes a fully-working agent demo that creates memories from natural conversation.

```bash
# Interactive mode (chat with Atlas, your AI assistant)
python agent_demo.py

# Auto mode (12 scripted turns, no LLM needed)
python agent_demo.py --auto

# What it demonstrates:
# - Pattern-based fact extraction from natural language
# - Automatic memory upsert via HttpClient
# - Hybrid semantic search on every turn
# - Memory graph link creation
# - Persistent user ID across runs (.agent_demo_user_id)
```

After running, open `http://localhost:8100/explorer/search` to see memories appear in real-time.

---

## Appendix B: Running Tests

```bash
# Unit tests (no PostgreSQL needed, fully mocked)
python -m pytest tests/unit -v

# Integration tests (requires running PostgreSQL)
python -m pytest tests/integration -v

# Specific test module
python -m pytest tests/unit/test_pip_package.py -v
python -m pytest tests/unit/test_data_masking.py -v

# Via Makefile
make test-unit
make test-integration

# Coverage report
python -m pytest tests/unit --cov=app --cov=agentmemodb --cov-report=html
```

**Test inventory:**

| Module | Tests | Focus |
|--------|-------|-------|
| `test_pip_package` | 111 | Embedded client, SQLiteStore, HttpClient, MemoryManager |
| `test_data_masking` | 60 | PII patterns, custom regex, audit, pipeline |
| `test_new_features` | 68 | MCP server, WebSocket, scheduler, settings |
| `test_state_transitions` | 24 | All valid + invalid task transitions |
| `test_scoring` | 7 | Score formula, recency decay, authority |
| `test_auth` | 7 | Key generation, hashing, scopes |

---

## Appendix C: Publishing the Pip Package to PyPI

```bash
# Prerequisites
pip install build twine

# Build wheel + sdist
python pkg/publish.py

# Validate
python pkg/publish.py --check

# Upload to TestPyPI (test first)
python pkg/publish.py --test-pypi

# Upload to real PyPI
python pkg/publish.py --pypi

# Set credentials
set TWINE_USERNAME=__token__
set TWINE_PASSWORD=pypi-your-token-here
```

**Version bump** — update in two places before releasing:
1. `pkg/pyproject.toml` → `version = "X.Y.Z"`
2. `agentmemodb/__init__.py` → `__version__ = "X.Y.Z"`

---

*AgentMemoryDB v0.1.0 — 190+ files · 19 database tables · 55+ REST endpoints · 314 tests*  
*GitHub: https://github.com/ioteverythin/agentmemorydb*
