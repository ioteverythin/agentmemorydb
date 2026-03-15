# AgentMemoryDB Documentation

Welcome to the AgentMemoryDB documentation. Use the guides below to learn how to use every feature.

---

## Getting Started

| Guide | Description |
|---|---|
| [Quick Start](quickstart.md) | Run in Docker and store your first memory in 5 minutes |

---

## Core Guides

| Guide | Description |
|---|---|
| [REST API Reference](rest-api.md) | Complete `curl` examples for all 50+ REST endpoints |
| [Python SDK Guide](python-sdk.md) | Embedded client, HTTP client, async SDK, and `MemoryManager` |
| [Framework Integrations](integrations.md) | LangChain and LangGraph drop-in components |
| [Advanced Features](advanced-features.md) | Events pipeline, graph traversal, bulk ops, webhooks, masking, and more |
| [MCP Server & WebSocket](mcp-websocket.md) | AI agent tools (MCP) and real-time event streaming |

---

## Reference

| Guide | Description |
|---|---|
| [Detailed Technical Reference](DETAILED_REFERENCE.md) | In-depth technical reference — scoring, schema, services, and internals |
| [Architecture](architecture.md) | System design diagrams and data flow |

---

## Feature Summary

### 🧠 Memory System
- **4 memory types**: semantic, episodic, procedural, working
- **4 scopes**: user, project, session, agent
- **Automatic versioning** — every upsert creates a new version, all history retained
- **Temporal validity** — memories with `valid_from`, `valid_to`, `expires_at`
- **Hybrid scoring** — vector similarity × recency × importance × authority × confidence

### 🔍 Search
- Semantic search via `sentence-transformers/all-MiniLM-L6-v2` (384-dim)
- Filter by type, scope, status, confidence, importance, metadata
- `explain: true` returns full score breakdown per result
- Bulk search — 20 queries in one request

### 🕸 Knowledge Graph
- Typed memory links: `supports`, `contradicts`, `derived_from`, `related_to`, `supersedes`
- BFS graph expansion with configurable depth and node limit
- Shortest-path queries between any two memories

### 🔄 Pipeline
- Event → Observation → Memory lifecycle
- Auto-extraction of structured observations from raw events
- Task state machine with full transition history

### 🛡 Security & Privacy
- PII masking (email, phone, SSN, credit card, IP, DOB)
- API key authentication with scoped permissions
- Row-level user isolation

### 📡 Real-Time
- WebSocket event streaming — subscribe by user, project, or memory
- Webhooks with HMAC-SHA256 signature verification and retry logic

### 🤖 AI Integrations
- **LangChain**: ChatHistory, Retriever, Memory Tool, ConversationMemory
- **LangGraph**: Store (persistent knowledge), Saver (graph state checkpoints)
- **MCP Server**: 7 tools for AI agents via Model Context Protocol
- **TypeScript SDK**: Full API coverage for Node.js and browser

### ⚙ Operations
- Background scheduler (deduplication, archival, recency, expiry, log pruning)
- Import/export (JSON, 3 strategies: upsert/skip/overwrite)
- Consolidation — detect and merge near-duplicate memories
- CLI tool for admin operations
- Prometheus metrics at `/metrics`

---

## Quick Reference

### Memory Types

| Type | Use for |
|---|---|
| `semantic` | Facts, preferences, knowledge (persists forever) |
| `episodic` | Events, conversations, past experiences |
| `procedural` | How-to steps, processes, instructions |
| `working` | Current-session temporary context |

### API Base URL
```
http://localhost:8100/api/v1/
```

### OpenAPI Interactive Docs
```
http://localhost:8100/docs
```

### Prometheus Metrics
```
http://localhost:8100/metrics
```

### WebSocket Event Stream
```
ws://localhost:8100/ws?channels=user:{user_id}
```
