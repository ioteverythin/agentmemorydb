# @agentmemorydb/sdk

TypeScript/JavaScript SDK for [AgentMemoryDB](https://github.com/agentmemorydb/agentmemorydb) — the SQL-native, auditable, event-sourced memory backend for agentic AI.

## Install

```bash
npm install @agentmemorydb/sdk
```

## Quick Start

```typescript
import { AgentMemoryDB } from '@agentmemorydb/sdk';

const db = new AgentMemoryDB({
  baseUrl: 'http://localhost:8000',
  apiKey: 'your-api-key',
});

// Store a memory
const memory = await db.memories.upsert({
  userId: '550e8400-e29b-41d4-a716-446655440000',
  memoryKey: 'user_preference_language',
  content: 'User prefers TypeScript for backend development',
  memoryType: 'semantic',
  confidence: 0.9,
});

// Search memories with hybrid scoring
const results = await db.memories.search({
  userId: '550e8400-e29b-41d4-a716-446655440000',
  queryText: 'What programming language does the user prefer?',
  topK: 5,
  explain: true,
});

// Real-time memory events
const ws = db.realtime(['user:550e8400-e29b-41d4-a716-446655440000']);
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Memory event:', data.event, data.data);
};
```

## Features

- **Full TypeScript types** for all API operations
- **Namespaced sub-clients**: `memories`, `events`, `links`, `graph`, `consolidation`, `data`
- **WebSocket real-time events** via `.realtime(channels)`
- **Hybrid search** with 5-signal scoring (vector + recency + importance + authority + confidence)
- **Automatic error handling** with typed `AgentMemoryDBError`

## API Reference

### `db.memories`
- `.upsert(input)` — Create or update a memory (versioned, deduplicated)
- `.search(input)` — Hybrid search with scoring
- `.get(id)` — Get a specific memory
- `.updateStatus(id, status)` — Change memory status
- `.versions(id)` — Get version history

### `db.events`
- `.create(input)` — Record an event into the pipeline
- `.list(params)` — List events with filters
- `.get(id)` — Get a specific event

### `db.links`
- `.create(input)` — Create a memory relationship
- `.list(memoryId)` — List links for a memory

### `db.graph`
- `.expand(input)` — BFS graph traversal from a memory
- `.shortestPath(sourceId, targetId)` — Find shortest path

### `db.consolidation`
- `.consolidate(input)` — Find & merge duplicate memories

### `db.data`
- `.export(userId)` — Export all user data
- `.import(data)` — Import from a previous export

## License

Apache-2.0
