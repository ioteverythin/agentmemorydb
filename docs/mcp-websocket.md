# MCP Server & WebSocket Real-Time Events

---

## Model Context Protocol (MCP) Server

AgentMemoryDB exposes a [Model Context Protocol](https://modelcontextprotocol.io) server that lets any MCP-compatible AI client (Claude Desktop, Cursor, custom agents) interact with memory operations using natural language-style tool calls.

### Starting the MCP Server

**Via Docker (runs alongside the main API automatically):**

```bash
docker compose up -d
# MCP server runs at ws://localhost:8100/mcp  (WebSocket transport)
# MCP server also available at http://localhost:8100/mcp (SSE/HTTP transport)
```

**Standalone (for development):**

```bash
python -m app.mcp.server
```

**With stdio transport** (for Claude Desktop / Cursor):

```bash
python -m app.mcp.server --transport stdio
```

### Connecting from Claude Desktop

Add to your Claude Desktop `config.json`:

```json
{
  "mcpServers": {
    "agentmemorydb": {
      "command": "python",
      "args": ["-m", "app.mcp.server", "--transport", "stdio"],
      "cwd": "/path/to/agentmemorydb",
      "env": {
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5433/agentmemodb"
      }
    }
  }
}
```

### Available MCP Tools

The server registers **7 tools** that AI agents can call:

---

#### `store_memory`

Store or update a memory in the agent's long-term memory system.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `user_id` | string (UUID) | ✓ | Memory owner |
| `memory_key` | string | ✓ | Unique key (e.g. `"pref:language"`) |
| `content` | string | ✓ | The memory text |
| `memory_type` | enum | | `working`, `episodic`, `semantic`, `procedural` |
| `scope` | enum | | `user`, `project`, `team`, `global` |
| `confidence` | float 0–1 | | Default: `0.7` |
| `importance_score` | float 0–1 | | Default: `0.5` |
| `source_type` | enum | | `human_input`, `agent_inference`, `system_inference`, `external_api`, `reflection`, `consolidated` |
| `project_id` | string (UUID) | | Optional project scope |
| `payload` | object | | Arbitrary JSON metadata |
| `is_contradiction` | bool | | Flags contradiction with existing memory |

**Example agent call:**
```json
{
  "tool": "store_memory",
  "arguments": {
    "user_id": "a1b2c3d4-...",
    "memory_key": "pref:language",
    "content": "User strongly prefers Python for backend work. Has 5 years experience.",
    "memory_type": "semantic",
    "confidence": 0.9,
    "importance_score": 0.85,
    "source_type": "agent_inference"
  }
}
```

**Response:**
```json
{
  "memory_id": "9086d314-...",
  "memory_key": "pref:language",
  "is_new": true,
  "version": 1,
  "status": "active",
  "message": "Memory created successfully."
}
```

---

#### `recall_memories`

Search and retrieve relevant memories using hybrid scoring (vector + recency + importance + authority + confidence).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `user_id` | string (UUID) | ✓ | Whose memories to search |
| `query_text` | string | | Natural language query |
| `memory_types` | string[] | | Filter by type |
| `scopes` | string[] | | Filter by scope |
| `top_k` | integer 1–100 | | Default: `10` |
| `min_confidence` | float 0–1 | | Minimum confidence threshold |
| `project_id` | string (UUID) | | Optional project filter |

**Example:**
```json
{
  "tool": "recall_memories",
  "arguments": {
    "user_id": "a1b2c3d4-...",
    "query_text": "What programming languages and frameworks does this user prefer?",
    "memory_types": ["semantic"],
    "top_k": 5
  }
}
```

**Response:**
```json
{
  "query": "What programming languages...",
  "total_candidates": 12,
  "results": [
    {
      "memory_id": "...",
      "memory_key": "pref:language",
      "memory_type": "semantic",
      "content": "User prefers Python for backend.",
      "confidence": 0.9,
      "importance": 0.85,
      "final_score": 0.923,
      "score_breakdown": {
        "vector": 0.95,
        "recency": 0.98,
        "importance": 0.85,
        "authority": 0.5,
        "confidence": 0.9
      }
    }
  ]
}
```

---

#### `get_memory`

Retrieve a specific memory by its ID.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `memory_id` | string (UUID) | ✓ | The memory to retrieve |

**Response includes:** id, key, type, scope, content, confidence, importance, status, version, created_at, updated_at, payload.

---

#### `link_memories`

Create a typed relationship between two memories in the knowledge graph.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `source_memory_id` | string (UUID) | ✓ | Source node |
| `target_memory_id` | string (UUID) | ✓ | Target node |
| `link_type` | enum | ✓ | `derived_from`, `contradicts`, `supports`, `related_to`, `supersedes` |
| `metadata` | object | | Optional metadata about the relationship |

**Example:**
```json
{
  "tool": "link_memories",
  "arguments": {
    "source_memory_id": "uuid-a",
    "target_memory_id": "uuid-b",
    "link_type": "supports",
    "metadata": {"explanation": "Both express preference for compiled languages"}
  }
}
```

---

#### `record_event`

Record a raw event into the memory pipeline (Event → Observation → Memory lifecycle).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `user_id` | string (UUID) | ✓ | Associated user |
| `content` | string | ✓ | Event content |
| `event_type` | enum | | `user_message`, `agent_message`, `tool_call`, `tool_result`, `system_event`, `observation`, `reflection` |
| `run_id` | string (UUID) | | Optional run ID |
| `metadata` | object | | Optional structured metadata |

**Example:**
```json
{
  "tool": "record_event",
  "arguments": {
    "user_id": "a1b2c3d4-...",
    "event_type": "user_message",
    "content": "I always write tests before code — TDD all the way.",
    "run_id": "run-uuid-..."
  }
}
```

---

#### `explore_graph`

Explore the memory knowledge graph using BFS traversal from a starting memory.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `memory_id` | string (UUID) | ✓ | Starting node |
| `max_depth` | integer 1–5 | | Default: `2` |
| `link_types` | string[] | | Filter to specific relationship types |

**Response:**
```json
{
  "origin": "uuid-seed",
  "max_depth": 2,
  "connected_memories": [
    {
      "memory_id": "...",
      "memory_key": "skill:python",
      "content": "Alice has 5 years Python experience",
      "memory_type": "semantic",
      "status": "active"
    }
  ],
  "total_found": 4
}
```

---

#### `consolidate_memories`

Find and merge duplicate or near-duplicate memories.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `user_id` | string (UUID) | ✓ | User to consolidate |
| `similarity_threshold` | float 0.5–1.0 | | Default: `0.92` |
| `dry_run` | bool | | Default: `true` (preview only) |

**Example:**
```json
{
  "tool": "consolidate_memories",
  "arguments": {
    "user_id": "a1b2c3d4-...",
    "dry_run": false
  }
}
```

**Response:**
```json
{
  "user_id": "a1b2c3d4-...",
  "dry_run": false,
  "duplicates_found": 3,
  "merged": 3,
  "details": []
}
```

---

### MCP Usage Pattern for AI Agents

A typical agent session using MCP tools:

```
1. Agent receives user message: "I prefer dark mode and Python"
2. Agent calls: store_memory("pref:ui", "User prefers dark mode")
3. Agent calls: store_memory("pref:language", "User prefers Python")
4. Agent answers the user

--- Later session ---

5. Agent receives: "What are my preferences?"
6. Agent calls: recall_memories(query="user preferences")
7. Agent uses results to personalize the response
```

---

## WebSocket Real-Time Events

Subscribe to live memory events without polling.

### Connecting

```
ws://localhost:8100/ws
ws://localhost:8100/ws?channels=user:USER-UUID,project:PROJECT-UUID
```

### JavaScript / Browser

```javascript
// Connect and subscribe to user events
const ws = new WebSocket(
  `ws://localhost:8100/ws?channels=user:${userId}`
);

ws.onopen = () => {
  console.log("Connected to AgentMemoryDB event stream");

  // Optionally subscribe to additional channels
  ws.send(JSON.stringify({
    action: "subscribe",
    channel: `project:${projectId}`,
  }));

  // Ping to test connection
  ws.send(JSON.stringify({ action: "ping" }));
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  switch (msg.event) {
    case "memory.created":
      console.log(`New memory: ${msg.memory_key}`);
      break;

    case "memory.updated":
      console.log(`Updated: ${msg.memory_key} v${msg.version}`);
      break;

    case "memory.archived":
      console.log(`Archived: ${msg.memory_id}`);
      break;

    case "pong":
      console.log(`Connected. Active connections: ${msg.active_connections}`);
      break;

    case "subscribed":
      console.log(`Subscribed to: ${msg.channel}`);
      break;

    case "unsubscribed":
      console.log(`Unsubscribed from: ${msg.channel}`);
      break;
  }
};

ws.onclose = () => {
  console.log("Disconnected");
};

ws.onerror = (err) => {
  console.error("WebSocket error:", err);
};
```

### Python (asyncio)

```python
import asyncio
import json
import websockets

async def listen():
    user_id = "YOUR-USER-UUID"

    async with websockets.connect(
        f"ws://localhost:8100/ws?channels=user:{user_id}"
    ) as ws:
        print("Connected to AgentMemoryDB event stream")

        # Ping
        await ws.send(json.dumps({"action": "ping"}))

        async for raw_message in ws:
            msg = json.loads(raw_message)
            event = msg.get("event", "")

            if event == "memory.created":
                print(f"✅ New memory: {msg.get('memory_key')} [{msg.get('memory_type')}]")

            elif event == "memory.updated":
                print(f"🔄 Updated: {msg.get('memory_key')} → v{msg.get('version')}")

            elif event == "memory.archived":
                print(f"📦 Archived: {msg.get('memory_id')}")

            elif event == "pong":
                print(f"🏓 Pong — active connections: {msg.get('active_connections')}")

asyncio.run(listen())
```

### Channel Patterns

| Channel | Events received |
|---|---|
| `user:{user_id}` | All events for a specific user |
| `project:{project_id}` | All events for a project |
| `memory:{memory_id}` | Updates to one specific memory |
| `global` | Every event (for admin monitoring) |

### WebSocket Commands

After connecting, send JSON commands:

```json
// Subscribe to a new channel
{"action": "subscribe", "channel": "user:abc-123"}

// Unsubscribe from a channel
{"action": "unsubscribe", "channel": "user:abc-123"}

// Test connectivity
{"action": "ping"}

// View connection stats
{"action": "status"}
```

### Status Response

```json
{
  "event": "status",
  "active_connections": 14,
  "subscriptions": {
    "user:abc-123": 2,
    "global": 1,
    "project:xyz": 3
  }
}
```

---

## Real-Time Dashboard Example

Here's a full example building a live memory dashboard using WebSocket + vanilla JavaScript:

```html
<!DOCTYPE html>
<html>
<head>
  <title>AgentMemoryDB Live Events</title>
  <style>
    #events { font-family: monospace; font-size: 13px; }
    .created { color: green; }
    .updated { color: blue; }
    .archived { color: orange; }
  </style>
</head>
<body>
  <h1>Memory Event Stream</h1>
  <div id="status">Connecting...</div>
  <div id="events"></div>

  <script>
    const userId = prompt("Enter your User ID:");
    const ws = new WebSocket(`ws://localhost:8100/ws?channels=user:${userId},global`);
    const eventsDiv = document.getElementById("events");
    const statusDiv = document.getElementById("status");

    ws.onopen = () => {
      statusDiv.textContent = "✅ Connected";
      ws.send(JSON.stringify({ action: "ping" }));
    };

    ws.onmessage = ({ data }) => {
      const msg = JSON.parse(data);
      const ts = new Date().toLocaleTimeString();

      let text = "";
      let cls = "";

      if (msg.event === "memory.created") {
        text = `[${ts}] ✅ CREATED ${msg.memory_key} (${msg.memory_type})`;
        cls = "created";
      } else if (msg.event === "memory.updated") {
        text = `[${ts}] 🔄 UPDATED ${msg.memory_key} → v${msg.version}`;
        cls = "updated";
      } else if (msg.event === "memory.archived") {
        text = `[${ts}] 📦 ARCHIVED ${msg.memory_id}`;
        cls = "archived";
      }

      if (text) {
        const div = document.createElement("div");
        div.className = cls;
        div.textContent = text;
        eventsDiv.prepend(div);
      }
    };

    ws.onclose = () => {
      statusDiv.textContent = "❌ Disconnected";
    };
  </script>
</body>
</html>
```

---

## MCP + WebSocket Combined Pattern

For agents that need both tools and real-time feedback:

```python
"""
Agent that stores memories via MCP tools AND receives
real-time confirmation via WebSocket.
"""
import asyncio
import json
import websockets
import httpx

async def agent_with_realtime_memory(user_id: str):
    """Agent using REST API for writes + WebSocket for confirmation."""

    received_events = []

    async def ws_listener():
        """Background task: listen for memory events."""
        async with websockets.connect(
            f"ws://localhost:8100/ws?channels=user:{user_id}"
        ) as ws:
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("event", "").startswith("memory."):
                    received_events.append(msg)
                    print(f"  📡 Event: {msg['event']} — {msg.get('memory_key', msg.get('memory_id'))}")

    # Start listener in background
    listener_task = asyncio.create_task(ws_listener())

    # Give WS time to connect
    await asyncio.sleep(0.3)

    # Write memories via REST
    async with httpx.AsyncClient(base_url="http://localhost:8100") as client:
        memories_to_store = [
            ("pref:language", "User prefers Python", 0.9),
            ("pref:framework", "User likes FastAPI", 0.85),
            ("skill:async", "Experienced with async Python", 0.8),
        ]

        for key, content, importance in memories_to_store:
            resp = await client.post("/api/v1/memories/upsert", json={
                "user_id": user_id,
                "memory_key": key,
                "memory_type": "semantic",
                "scope": "user",
                "content": content,
                "importance_score": importance,
            })
            resp.raise_for_status()
            print(f"  📝 Stored: {key}")
            await asyncio.sleep(0.1)

    # Wait for events to arrive
    await asyncio.sleep(0.5)
    listener_task.cancel()

    print(f"\n✅ Stored {len(memories_to_store)} memories")
    print(f"📡 Received {len(received_events)} real-time confirmations")

asyncio.run(agent_with_realtime_memory("YOUR-USER-UUID"))
```
