# QuickStart — AgentMemoryDB

Get from zero to a working memory-enabled agent in under 5 minutes.

---

## Prerequisites

| Requirement | Version |
|---|---|
| Docker Desktop | 24+ |
| Docker Compose | v2 |
| Python (optional) | 3.11+ |
| curl / httpie | any |

---

## 1. Start the Server

```bash
# Clone and enter the project
git clone https://github.com/ioteverythin/agentmemorydb.git
cd agentmemorydb

# Start PostgreSQL + API server (pulls pre-built image or builds locally)
docker compose up -d

# Verify both containers are healthy (wait ~15 seconds on first boot)
docker compose ps
```

Expected output:
```
NAME                     STATUS
agentmemodb-postgres-1   Up (healthy)
agentmemodb-app-1        Up (healthy)
```

The API is now live at **http://localhost:8100**.

---

## 2. Verify Health

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

---

## 3. Create Your First User

Every memory is owned by a user. Create one to get started:

```bash
curl -s -X POST http://localhost:8100/api/v1/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice"}' | python -m json.tool
```

```json
{
  "id": "a1b2c3d4-...",
  "name": "Alice",
  "created_at": "2025-01-01T00:00:00Z"
}
```

> **Save the `id` field** — you'll use it as `USER_ID` in all subsequent calls.

```bash
export USER_ID="a1b2c3d4-..."    # Linux/macOS
$env:USER_ID = "a1b2c3d4-..."    # PowerShell
```

---

## 4. Store Your First Memory

```bash
curl -s -X POST http://localhost:8100/api/v1/memories/upsert \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"memory_key\": \"pref:language\",
    \"memory_type\": \"semantic\",
    \"scope\": \"user\",
    \"content\": \"Alice prefers Python for backend development and TypeScript for frontend.\",
    \"importance_score\": 0.8,
    \"confidence\": 0.9
  }"
```

Response:
```json
{
  "id": "9086d314-...",
  "memory_key": "pref:language",
  "memory_type": "semantic",
  "content": "Alice prefers Python for backend development and TypeScript for frontend.",
  "version": 1,
  "status": "active",
  "importance_score": 0.8,
  "confidence": 0.9
}
```

---

## 5. Search Memories (Hybrid Semantic Search)

```bash
curl -s -X POST http://localhost:8100/api/v1/memories/search \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"query_text\": \"What programming languages does Alice like?\",
    \"top_k\": 5,
    \"explain\": true
  }"
```

Response:
```json
{
  "results": [
    {
      "memory": {
        "id": "9086d314-...",
        "memory_key": "pref:language",
        "content": "Alice prefers Python for backend development and TypeScript for frontend."
      },
      "score": {
        "final_score": 0.847,
        "vector_score": 0.921,
        "recency_score": 1.0,
        "importance_score": 0.8,
        "authority_score": 0.25,
        "confidence_score": 0.9
      }
    }
  ],
  "total_candidates": 1
}
```

The `explain: true` flag returns a full **score breakdown** showing exactly how each result was ranked.

---

## 6. Load Some Demo Data (Optional)

The included demo script seeds 9 memories with real semantic embeddings and creates a knowledge graph with 7 typed links:

```bash
docker exec agentmemodb-app-1 python examples/scripts/agent_demo.py --auto
```

---

## 7. Explore the UI

Open the built-in Explorer at **http://localhost:8100/explorer** (or open the frontend in development):

- Browse memories by user
- Run semantic searches
- Visualize the memory graph
- View version history
- Monitor Prometheus metrics at `http://localhost:8100/metrics`
- View OpenAPI docs at `http://localhost:8100/docs`

---

## 8. Python SDK Quick Start

Install the SDK (or use the one included in the repo):

```python
# Option A: Embedded client (SQLite, zero dependencies, no server needed)
import agentmemodb

db = agentmemodb.Client()                  # creates ./agentmemodb_data/
db.upsert("user-1", "pref:lang", "User prefers Python")
results = db.search("user-1", "What language?")
for r in results:
    print(f"{r.key}: {r.content}  (score={r.score:.3f})")
db.close()
```

```python
# Option B: Async HTTP client (connects to Docker server)
import asyncio
from app.sdk.client import AgentMemoryDBClient

async def main():
    async with AgentMemoryDBClient("http://localhost:8100") as client:
        user = await client.create_user("Alice")
        user_id = user["id"]

        await client.upsert_memory(
            user_id=user_id,
            memory_key="pref:language",
            content="Alice prefers Python.",
            memory_type="semantic",
            importance_score=0.8,
        )

        results = await client.search_memories(
            user_id=user_id,
            query="What language does Alice prefer?",
            explain=True,
        )
        print(results)

asyncio.run(main())
```

---

## What's Next

| Guide | Description |
|---|---|
| [REST API Reference](rest-api.md) | Complete curl examples for all 50+ endpoints |
| [Python SDK Guide](python-sdk.md) | Async SDK, embedded client, MemoryManager |
| [Integrations](integrations.md) | LangChain, LangGraph drop-in components |
| [Advanced Features](advanced-features.md) | Graph, bulk ops, webhooks, masking, consolidation |
| [MCP & WebSocket](mcp-websocket.md) | AI agent tools and real-time events |
| [Architecture](architecture.md) | System design and data flow |
| [Detailed Reference](DETAILED_REFERENCE.md) | Complete technical reference |
