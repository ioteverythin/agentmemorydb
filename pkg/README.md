# AgentMemoryDB

**Lightweight, embeddable memory backend for AI agents.**

Short-term conversation buffer + long-term knowledge store + semantic search + PII masking — all in a single pip install, no server required.

[![PyPI version](https://badge.fury.io/py/agentmemodb.svg)](https://pypi.org/project/agentmemodb/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

---

## Install

```bash
pip install agentmemodb                     # core (SQLite embedded, zero config)
pip install agentmemodb[openai]             # + OpenAI embeddings
pip install agentmemodb[huggingface]        # + HuggingFace sentence-transformers
pip install agentmemodb[langchain]          # + LangChain integration
pip install agentmemodb[langgraph]          # + LangGraph integration
pip install agentmemodb[remote]             # + connect to AgentMemoryDB server
pip install agentmemodb[all]                # everything
```

## Quick Start

### Embedded Mode (SQLite, zero config)

```python
import agentmemodb

db = agentmemodb.Client()                       # stores in ./agentmemodb_data/
db = agentmemodb.Client(path=":memory:")        # in-memory (for tests)

# Store memories
db.upsert("user-1", "pref:lang", "User prefers Python", memory_type="semantic")
db.upsert("user-1", "pref:editor", "User uses VS Code", importance=0.9)

# Semantic search
results = db.search("user-1", "What programming language?", top_k=5)
for r in results:
    print(f"  {r.key}: {r.content}  (score={r.score:.3f})")

# CRUD
mem = db.get("user-1", "pref:lang")
all_mems = db.list("user-1", memory_type="semantic")
db.delete("user-1", "pref:lang")
n = db.count("user-1")

db.close()
```

### Remote Mode (connect to server)

```python
db = agentmemodb.HttpClient("http://localhost:8100", api_key="amdb_...")

# Same API as embedded!
db.upsert("user-1", "pref:lang", "User prefers Python")
results = db.search("user-1", "language?")
db.close()
```

---

## MemoryManager — Short-term + Long-term

A unified interface that combines conversation history (short-term) with persistent knowledge (long-term):

```python
from agentmemodb import MemoryManager

with MemoryManager("user-1") as mgr:
    # ── Short-term: conversation buffer ──
    mgr.short_term.add_system("You are a helpful assistant.")
    mgr.short_term.add_user("I'm building an API with FastAPI.")
    mgr.short_term.add_assistant("Great choice! Need help with auth?")

    # Export as OpenAI-compatible message list
    messages = mgr.short_term.to_list()
    # [{"role": "system", "content": "..."}, {"role": "user", ...}, ...]

    # ── Long-term: persistent knowledge ──
    mgr.long_term.remember("pref:framework", "User prefers FastAPI", importance=0.9)
    mgr.long_term.remember("skill:python", "Expert Python developer")

    results = mgr.long_term.recall("What framework?")

    # ── Promote conversation insights → long-term ──
    mgr.promote("insight:auth", "Use JWT with OAuth2 for FastAPI")

    # ── Combined context window for LLM ──
    ctx = mgr.get_context_window("How to set up auth?", n_messages=10, n_memories=5)
    # ctx = {"messages": [...], "relevant_memories": [...], "stats": {...}}
```

---

## LangChain Integration

```python
from agentmemodb import Client
from agentmemodb.integrations.langchain import (
    AgentMemoryDBChatHistory,
    AgentMemoryDBRetriever,
    AgentMemoryDBConversationMemory,
    create_memory_tool,
)

db = Client(path=":memory:")

# Chat history (BaseChatMessageHistory)
history = AgentMemoryDBChatHistory(client=db, user_id="u1", session_id="s1")
history.add_user_message("Hello!")
history.add_ai_message("Hi there!")
messages = history.messages  # [HumanMessage, AIMessage]

# Retriever (semantic search → Documents)
retriever = AgentMemoryDBRetriever(client=db, user_id="u1", top_k=5)
docs = retriever.invoke("What does the user prefer?")

# Memory tool (for agents)
tool = create_memory_tool(db, user_id="u1")
# Agent can call: tool('{"action": "store", "key": "k", "content": "v"}')
# Agent can call: tool('{"action": "recall", "query": "q"}')

# Conversation memory (history + relevant knowledge)
memory = AgentMemoryDBConversationMemory(client=db, user_id="u1", session_id="s1")
variables = memory.load_memory_variables({"input": "question"})
# {"history": "...", "relevant_context": "..."}
```

---

## LangGraph Integration

```python
from agentmemodb import Client
from agentmemodb.integrations.langgraph import (
    AgentMemoryDBStore,
    AgentMemoryDBSaver,
    create_memory_node,
    create_save_memory_node,
)

db = Client(path=":memory:")

# Store (long-term memory for graph nodes)
store = AgentMemoryDBStore(client=db, user_id="agent-1")
store.put("user:name", "Josh — full-stack developer")
results = store.search("Who is the user?", top_k=3)
context = store.search_as_text("user preferences")  # formatted for prompts

# Checkpoint saver (persist graph state)
saver = AgentMemoryDBSaver(client=db, user_id="system")
config = {"configurable": {"thread_id": "thread-1"}}
saver.put(config, {"messages": ["Hi!"], "step": 1}, metadata={"node": "start"})
state = saver.get(config)  # restore latest checkpoint

# Memory nodes (plug into StateGraph)
recall = create_memory_node(store, input_key="input", context_key="context")
save = create_save_memory_node(store, content_key="output")

from langgraph.graph import StateGraph, END
graph = StateGraph(...)
graph.add_node("recall", recall)
graph.add_node("generate", my_llm_node)
graph.add_node("save", save)
```

---

## PII Masking

Built-in write-time PII detection and replacement — personal data never reaches the database:

```python
db = agentmemodb.Client(mask_pii=True)
db.upsert("u1", "contact", "Email josh@company.com, SSN 123-45-6789")
mem = db.get("u1", "contact")
print(mem.content)  # "Email [EMAIL], SSN [SSN]"
```

Detects: email, phone, SSN, credit card, IP address, passport, date of birth.

---

## Embedding Providers

| Provider | Install | Usage |
|----------|---------|-------|
| **Dummy** (default) | — | `Client()` — hash-based, no API key |
| **OpenAI** | `pip install agentmemodb[openai]` | `Client(embedding_fn=OpenAIEmbedding(api_key="sk-..."))` |
| **HuggingFace** | `pip install agentmemodb[huggingface]` | Custom: see below |
| **Custom** | — | Any callable matching `EmbeddingFunction` protocol |

### Custom Embedding Example

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

class MyEmbedding:
    @property
    def dimension(self) -> int:
        return model.get_sentence_embedding_dimension()

    def __call__(self, texts: list[str]) -> list[list[float]]:
        return model.encode(texts, normalize_embeddings=True).tolist()

db = agentmemodb.Client(embedding_fn=MyEmbedding())
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Embedded mode** | SQLite + NumPy, zero config, `pip install` and go |
| **Remote mode** | Connect to AgentMemoryDB server via HTTP |
| **Short-term memory** | Conversation buffer with thread isolation, role filtering |
| **Long-term memory** | Persistent semantic knowledge with importance/confidence scores |
| **MemoryManager** | Unified short+long-term with `promote()` and `get_context_window()` |
| **Semantic search** | Cosine similarity over embeddings with configurable top-k |
| **Memory versioning** | Content-hash dedup, automatic version snapshots |
| **PII masking** | 7 built-in patterns, write-time replacement, no PII stored |
| **LangChain** | ChatHistory, Retriever, Tool, ConversationMemory |
| **LangGraph** | Store, Saver (checkpoints), Memory Nodes, StateGraph helpers |
| **Typed memories** | `semantic`, `episodic`, `procedural`, `working` |
| **Scopes** | `user`, `project`, `global`, `session` |
| **Type hints** | Full `py.typed` support for IDE autocompletion |

---

## API Reference

### Client / HttpClient

| Method | Description |
|--------|-------------|
| `upsert(user_id, key, content, ...)` | Create or update a memory |
| `search(user_id, query, top_k=10)` | Semantic search |
| `get(user_id, key)` | Get by user_id + key |
| `get_by_id(memory_id)` | Get by UUID |
| `list(user_id, ...)` | List with filters |
| `delete(user_id, key)` | Delete a memory |
| `count(user_id)` | Count memories |
| `close()` | Release resources |

### MemoryManager

| Method | Description |
|--------|-------------|
| `.short_term` | `ShortTermMemory` — `add_user()`, `add_assistant()`, `get_messages()`, `to_list()`, `to_string()` |
| `.long_term` | `LongTermMemory` — `remember()`, `recall()`, `get()`, `forget()`, `list_all()` |
| `promote(key, content)` | Move insight from conversation → long-term |
| `get_context_window(query)` | Combined messages + relevant memories for LLM |
| `new_thread(thread_id)` | Start a new conversation thread |
| `reset()` | Clear everything |

---

## Full Server

AgentMemoryDB also runs as a **full server** with PostgreSQL + pgvector, FastAPI, WebSocket, MCP protocol, React UI, and 55+ REST endpoints. See the [full documentation](https://github.com/agentmemorydb/agentmemorydb) for details.

---

## License

Apache 2.0 — see [LICENSE](https://github.com/agentmemorydb/agentmemorydb/blob/main/LICENSE).
