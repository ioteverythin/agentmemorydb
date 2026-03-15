"""AgentMemoryDB — pip-installable memory backend for agentic AI.

Two modes, one API
==================

**Embedded** (SQLite, zero config — like ChromaDB)::

    import agentmemodb

    db = agentmemodb.Client()                     # default: ./agentmemodb_data/
    db = agentmemodb.Client(path=":memory:")      # in-memory (for tests)
    db = agentmemodb.Client(path="./memories")    # custom directory

    db.upsert("user-1", "pref:lang", "User prefers Python")
    results = db.search("user-1", "What language?")
    for r in results:
        print(f"  {r.key}: {r.content}  (score={r.score:.3f})")
    db.close()

**Remote** (connect to a running AgentMemoryDB server)::

    db = agentmemodb.HttpClient("http://localhost:8100", api_key="amdb_...")
    results = db.search("user-1", "language?")

Both clients expose the **same** methods: ``upsert``, ``search``,
``get``, ``list``, ``delete``, ``count``, ``close``.
"""

__version__ = "0.1.0"

from agentmemodb.client import Client
from agentmemodb.http_client import HttpClient
from agentmemodb.types import Memory, MemoryVersion, SearchResult
from agentmemodb.embeddings import DummyEmbedding, OpenAIEmbedding
from agentmemodb.memory_manager import (
    ShortTermMemory,
    LongTermMemory,
    MemoryManager,
)

__all__ = [
    # Clients
    "Client",
    "HttpClient",
    # Memory manager
    "MemoryManager",
    "ShortTermMemory",
    "LongTermMemory",
    # Types
    "Memory",
    "MemoryVersion",
    "SearchResult",
    # Embeddings
    "DummyEmbedding",
    "OpenAIEmbedding",
]
