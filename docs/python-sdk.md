# Python SDK Guide

AgentMemoryDB ships with three Python clients:

| Client | When to use |
|---|---|
| `agentmemodb.Client` | Local / embedded use. SQLite, no server, no Docker. |
| `agentmemodb.HttpClient` | Synchronous HTTP client talking to the Docker server. |
| `app.sdk.client.AgentMemoryDBClient` | Async HTTP client for high-performance, async applications. |
| `agentmemodb.MemoryManager` | High-level abstraction combining short-term and long-term memory. |

---

## Installation

```bash
# For the embedded client (no server needed)
pip install agentmemodb

# For sentence-transformer embeddings (recommended)
pip install sentence-transformers

# For the async HTTP SDK (connects to Docker server)
pip install httpx
```

---

## 1. Embedded Client (`agentmemodb.Client`)

Zero-configuration, in-process memory backed by SQLite. No Docker, no PostgreSQL.

### Initializing

```python
import agentmemodb

# Default: stores to ./agentmemodb_data/agentmemodb.sqlite3
db = agentmemodb.Client()

# Custom path
db = agentmemodb.Client(path="./my_app/memories")

# In-memory (for tests)
db = agentmemodb.Client(path=":memory:")

# With sentence-transformer embeddings
from sentence_transformers import SentenceTransformer

class STEmbedding:
    dimension = 384
    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
    def __call__(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts).tolist()

db = agentmemodb.Client(embedding_fn=STEmbedding())

# With automatic PII masking
db = agentmemodb.Client(mask_pii=True)
```

### Storing Memories

```python
# Upsert by key — creates or updates
mem = db.upsert(
    user_id="user-1",
    key="pref:language",
    content="Alice prefers Python for backend, TypeScript for frontend.",
    memory_type="semantic",   # semantic | episodic | procedural | working
    scope="user",             # user | project | global | session
    importance=0.8,
    confidence=0.9,
    metadata={"source": "onboarding", "verified": True},
)
print(f"Stored: {mem.key} v{mem.version}")

# Multiple memory types
db.upsert("user-1", "episode:meeting-2025-01-01",
          "Met with the team. Decided to migrate to PostgreSQL.",
          memory_type="episodic")

db.upsert("user-1", "proc:deploy-steps",
          "1. Run tests 2. Build Docker image 3. Push to registry 4. Deploy",
          memory_type="procedural")

db.upsert("user-1", "ctx:current-task",
          "Currently debugging async race condition in the websocket handler",
          memory_type="working",
          scope="session")
```

### Searching Memories

```python
# Semantic search
results = db.search("user-1", "What programming languages does Alice know?", top_k=5)

for r in results:
    print(f"[{r.score:.3f}] {r.key}: {r.content}")

# Filter by memory type
results = db.search(
    "user-1",
    "deploy procedure",
    top_k=3,
    memory_types=["procedural"],
)

# Filter by scope
results = db.search(
    "user-1",
    "current task",
    top_k=3,
    scopes=["session"],
)
```

`SearchResult` fields:
| Field | Type | Description |
|---|---|---|
| `r.id` | str | Memory UUID |
| `r.key` | str | The memory key |
| `r.content` | str | Memory text |
| `r.score` | float | Relevance score (0.0–1.0) |
| `r.memory` | Memory | Full Memory object |
| `r.memory.memory_type` | str | `semantic`, `episodic`, etc. |
| `r.memory.importance` | float | Importance score |
| `r.memory.confidence` | float | Confidence score |
| `r.memory.version` | int | Current version number |

### Getting, Listing, Deleting

```python
# Get by key
mem = db.get("user-1", "pref:language")
if mem:
    print(f"{mem.key}: {mem.content} (v{mem.version})")

# List all memories
memories = db.list("user-1", limit=100)

# List by type
procedural = db.list("user-1", memory_type="procedural")

# List by scope
session_ctx = db.list("user-1", scope="session")

# Count
n = db.count("user-1")
print(f"Total: {n} memories")

# Delete a memory by key
deleted = db.delete("user-1", "ctx:current-task")
print(f"Deleted: {deleted}")

# Get version history
versions = db.versions("user-1", "pref:language")
for v in versions:
    print(f"  v{v['version']}: {v['content'][:60]}")
```

### Closing

```python
db.close()

# Or use as a context manager
with agentmemodb.Client() as db:
    db.upsert("user-1", "key", "content")
    # auto-closes
```

---

## 2. HTTP Client (`agentmemodb.HttpClient`)

Synchronous client that talks to the running Docker server. Ideal for scripts, notebooks, and synchronous frameworks (Flask, Django).

```python
from agentmemodb import HttpClient

client = HttpClient(
    base_url="http://localhost:8100",
    api_key="amdb_your_key_here",   # optional
    timeout=30.0,
)
```

### Core Operations

```python
# Health check
status = client.health()

# User management
user = client.create_user("Alice")
user_id = user["id"]

# Project
project = client.create_project(user_id, "Code Assistant")
project_id = project["id"]

# Upsert memory
mem = client.upsert(
    user_id,
    "pref:language",
    "Alice prefers Python.",
    memory_type="semantic",
    importance=0.85,
)

# Search
results = client.search(user_id, "Python preferences", top_k=5)

# List
memories = client.list(user_id, memory_type="semantic", limit=50)

# Get
mem = client.get(user_id, "pref:language")

# Delete
client.delete(user_id, "pref:language")

# Close
client.close()
```

---

## 3. Async HTTP Client (`AgentMemoryDBClient`)

High-performance async client using `httpx`. Best for FastAPI, async frameworks, and high-throughput pipelines.

```python
import asyncio
from app.sdk.client import AgentMemoryDBClient

async def main():
    async with AgentMemoryDBClient(
        base_url="http://localhost:8100",
        api_key="amdb_your_key_here",   # optional
        timeout=30.0,
    ) as client:

        # ── Users & Projects ────────────────────────────────
        user = await client.create_user("Alice")
        user_id = user["id"]

        project = await client.create_project(
            user_id=user_id,
            name="Code Assistant",
            description="AI coding assistant",
        )
        project_id = project["id"]

        # ── Runs ────────────────────────────────────────────
        run = await client.create_run(
            user_id=user_id,
            agent_name="coding-assistant",
            project_id=project_id,
        )
        run_id = run["id"]

        # ── Events ──────────────────────────────────────────
        event = await client.create_event(
            run_id=run_id,
            user_id=user_id,
            event_type="user_message",
            content="I prefer async Python over sync patterns.",
        )
        event_id = event["id"]

        # ── Observations ────────────────────────────────────
        observations = await client.extract_observations(event_id)

        # ── Memories ────────────────────────────────────────
        mem = await client.upsert_memory(
            user_id=user_id,
            memory_key="pref:async",
            content="Alice prefers async Python patterns.",
            memory_type="semantic",
            scope="user",
            importance_score=0.8,
            confidence=0.9,
        )
        memory_id = mem["id"]

        # Get by ID
        mem = await client.get_memory(memory_id)

        # List memories
        memories = await client.list_memories(
            user_id=user_id,
            memory_type="semantic",
            limit=50,
        )

        # Search
        results = await client.search_memories(
            user_id=user_id,
            query="What does Alice prefer in Python?",
            top_k=10,
            explain=True,
            memory_types=["semantic"],
        )

        # Update status
        await client.update_memory_status(memory_id, "archived")

        # Get version history
        versions = await client.get_memory_versions(memory_id)

        # Get links
        links = await client.get_memory_links(memory_id)

        # ── Bulk Operations ─────────────────────────────────
        batch_result = await client.batch_upsert([
            {
                "user_id": user_id,
                "memory_key": "skill:python",
                "memory_type": "semantic",
                "scope": "user",
                "content": "Alice has 5 years of Python experience",
                "importance_score": 0.8,
            },
            {
                "user_id": user_id,
                "memory_key": "skill:fastapi",
                "memory_type": "semantic",
                "scope": "user",
                "content": "Alice is proficient in FastAPI",
                "importance_score": 0.7,
            },
        ])
        print(f"Created: {batch_result['created']}, Updated: {batch_result['updated']}")

        multi_search = await client.batch_search([
            {"user_id": user_id, "query_text": "Python skills", "top_k": 3},
            {"user_id": user_id, "query_text": "TypeScript skills", "top_k": 3},
        ])

        # ── Graph ────────────────────────────────────────────
        graph = await client.expand_graph(
            seed_memory_id=memory_id,
            max_hops=2,
            max_nodes=30,
        )

        path = await client.shortest_path(
            source_id=mem_a_id,
            target_id=mem_b_id,
            max_depth=5,
        )

        # ── Tasks ────────────────────────────────────────────
        task = await client.create_task(
            user_id=user_id,
            title="Summarize meeting",
            run_id=run_id,
            priority=2,
        )
        task_id = task["id"]

        await client.transition_task(
            task_id=task_id,
            to_state="in_progress",
            reason="Processing started",
        )

        # ── Import / Export ──────────────────────────────────
        export_data = await client.export_memories(
            user_id=user_id,
            include_versions=True,
            include_links=True,
        )

        import_result = await client.import_memories(
            user_id=new_user_id,
            data=export_data,
            strategy="upsert",
        )

        # ── Webhooks ─────────────────────────────────────────
        webhook = await client.register_webhook(
            user_id=user_id,
            url="https://your-server.com/hooks/memory",
            events="memory.created,memory.updated",
            secret="my-secret-key",
        )

        webhooks = await client.list_webhooks(user_id)

        # ── Consolidation ────────────────────────────────────
        duplicates = await client.find_duplicates(user_id)
        result = await client.auto_consolidate(user_id)

        # ── Complete run ─────────────────────────────────────
        await client.complete_run(
            run_id=run_id,
            summary="Session complete. Stored 5 new preferences.",
        )

asyncio.run(main())
```

---

## 4. MemoryManager

`MemoryManager` is a high-level abstraction that combines short-term conversation memory and long-term persistent memory into a single easy-to-use interface.

```python
from agentmemodb import MemoryManager

mgr = MemoryManager(
    user_id="user-1",
    db_path=None,           # auto-creates ./agentmemodb_data/
    thread_id="session-1",  # conversation thread
    max_short_term=50,      # max messages in short-term buffer
)
```

### Short-Term Memory (Conversation Buffer)

```python
# Add messages (ordered, scoped to a thread)
mgr.short_term.add("user", "I prefer Python for backend work.")
mgr.short_term.add("assistant", "Got it — Python for backend. TypeScript for frontend?")
mgr.short_term.add("user", "Yes, exactly.")

# Convenient shortcuts
mgr.short_term.add_user("What was that Python library we discussed?")
mgr.short_term.add_assistant("You mentioned FastAPI for the API layer.")
mgr.short_term.add_system("System context: User is an experienced developer.")
mgr.short_term.add_tool('{"result": "success", "function": "run_tests"}')

# Retrieve messages
messages = mgr.short_term.get_messages(limit=20)
last_5 = mgr.short_term.get_last(5)

# Filter by role
user_msgs = mgr.short_term.get_messages(roles=["user"])

# Count
n = mgr.short_term.count()

# Export as list (OpenAI/LangChain format)
msg_list = mgr.short_term.to_list()
# [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]

# Export as formatted string (for prompt injection)
history_str = mgr.short_term.to_string()
# "user: I prefer Python...\nassistant: Got it..."

# Start a new thread (same user)
new_thread = mgr.short_term.new_thread()

# Clear conversation
mgr.short_term.clear()
```

### Long-Term Memory (Persistent Knowledge)

```python
# Store persistent knowledge
mgr.long_term.remember(
    key="pref:language",
    content="User strongly prefers Python for backend development.",
    memory_type="semantic",
    importance=0.9,
)

mgr.long_term.remember(
    key="pref:tools",
    content="Favorite tools: FastAPI, SQLAlchemy, pytest, ruff",
    memory_type="semantic",
    importance=0.8,
)

# Recall (semantic search)
results = mgr.long_term.recall(
    "What languages and tools does the user prefer?",
    top_k=5,
)
for r in results:
    print(f"[{r.score:.3f}] {r.key}: {r.content}")

# Get specific key
mem = mgr.long_term.get("pref:language")

# Check if exists
exists = mgr.long_term.has("pref:language")

# List all long-term memories
all_memories = mgr.long_term.list(limit=100)

# Forget (delete)
mgr.long_term.forget("pref:old-irrelevant-info")

# Count
n = mgr.long_term.count()
```

### Promoting Short-Term to Long-Term

Extract and persist an insight from the conversation:

```python
# Manually promote a key insight
mgr.promote(
    key="pref:async_patterns",
    content="User strongly prefers async/await over callbacks.",
    importance=0.85,
    memory_type="semantic",
)
```

### Full Workflow Example

```python
from agentmemodb import MemoryManager
import openai

def build_prompt(mgr: MemoryManager, user_query: str) -> str:
    # 1. Get relevant long-term memories
    memories = mgr.long_term.recall(user_query, top_k=5)
    memory_context = "\n".join(
        f"- {r.content} (relevance={r.score:.2f})"
        for r in memories
    )

    # 2. Get recent conversation history
    history = mgr.short_term.to_string(separator="\n")

    return f"""## Relevant memory context:
{memory_context}

## Recent conversation:
{history}

## User:
{user_query}"""

def chat(user_id: str):
    with MemoryManager(user_id=user_id) as mgr:
        while True:
            user_input = input("You: ")
            if user_input.lower() in ("quit", "exit"):
                break

            # Add to conversation buffer
            mgr.short_term.add_user(user_input)

            # Build context-aware prompt
            prompt = build_prompt(mgr, user_input)

            # Call LLM
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
            )
            ai_response = response.choices[0].message.content

            # Add AI response to buffer
            mgr.short_term.add_assistant(ai_response)
            print(f"AI: {ai_response}")

            # Auto-extract any preferences/facts to long-term
            # (production: run an extraction model here)

chat("user-1")
```

---

## 5. Memory Types Reference

| Type | Use Case | Examples |
|---|---|---|
| `semantic` | Persistent facts, preferences, knowledge | "User prefers Python", "Company uses AWS" |
| `episodic` | Specific events, conversations, past experiences | "Meeting on 2025-01-01 about migration plan" |
| `procedural` | How-to knowledge, steps, processes | "Deploy steps: 1. Build 2. Push 3. Run" |
| `working` | Temporary context for current session | "Currently debugging websocket handler" |

## 6. Scope Reference

| Scope | Visibility |
|---|---|
| `user` | Persists across all sessions for this user |
| `project` | Scoped to a specific project/workspace |
| `session` | Temporary, session-only memory |
| `agent` | Specific to one agent instance |

## 7. Source Type Reference

| Source | Meaning |
|---|---|
| `human_input` | Directly stated by the human user |
| `agent_inference` | Inferred by an AI agent during reasoning |
| `system_inference` | Extracted by system pipeline (event → observation) |
| `external_api` | Imported from external data source |
| `reflection` | Generated during agent self-reflection step |
| `consolidated` | Created by merging duplicate memories |

---

## 8. Complete Example: Agent with Memory

```python
"""
A complete agent that uses AgentMemoryDB for persistent memory
across conversation sessions.
"""
import agentmemodb
from agentmemodb import MemoryManager
from sentence_transformers import SentenceTransformer


class STEmbedding:
    """Sentence-transformer embedding wrapper."""
    dimension = 384

    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

    def __call__(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts).tolist()


def create_agent(user_id: str):
    """Create a memory-enabled agent for a user."""
    embedding_fn = STEmbedding()
    db = agentmemodb.Client(
        path="./agent_memories",
        embedding_fn=embedding_fn,
        mask_pii=True,          # auto-mask PII before storage
    )
    return MemoryManager(user_id=user_id, client=db)


def remember_preferences(mgr: MemoryManager, conversation_turn: dict):
    """Extract and store any preferences from a conversation turn."""
    user_msg = conversation_turn.get("user", "")

    # Simple keyword-based extraction (use an LLM in production)
    if "prefer" in user_msg.lower() or "like" in user_msg.lower():
        mgr.long_term.remember(
            key=f"pref:extracted:{hash(user_msg) % 10000:04d}",
            content=user_msg,
            memory_type="semantic",
            importance=0.7,
        )


if __name__ == "__main__":
    agent = create_agent("alice")

    # Seed some initial knowledge
    agent.long_term.remember("pref:language", "Alice prefers Python")
    agent.long_term.remember("skill:python", "Alice has 5 years Python experience")
    agent.long_term.remember("pref:framework", "Alice likes FastAPI for APIs")

    # Search for relevant context
    query = "What Python frameworks does Alice know?"
    results = agent.long_term.recall(query, top_k=3)

    print(f"Query: {query}")
    print("Relevant memories:")
    for r in results:
        print(f"  [{r.score:.3f}] {r.key}: {r.content}")

    agent.close()
```
