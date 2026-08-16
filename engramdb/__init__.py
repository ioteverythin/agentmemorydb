"""EngramDB — pip-installable memory backend for agentic AI.

Two modes, one API
==================

**Embedded** (SQLite, zero config — like ChromaDB)::

    import engramdb

    db = engramdb.Client()                     # default: ./engramdb_data/
    db = engramdb.Client(path=":memory:")      # in-memory (for tests)
    db = engramdb.Client(path="./memories")    # custom directory

    db.upsert("user-1", "pref:lang", "User prefers Python")
    results = db.search("user-1", "What language?")
    for r in results:
        print(f"  {r.key}: {r.content}  (score={r.score:.3f})")
    db.close()

**Remote** (connect to a running EngramDB server)::

    db = engramdb.HttpClient("http://localhost:8100", api_key="amdb_...")
    results = db.search("user-1", "language?")

Both clients expose the **same** methods: ``upsert``, ``search``,
``get``, ``list``, ``delete``, ``count``, ``close``.
"""

__version__ = "0.1.0"

from engramdb.client import Client
from engramdb.http_client import HttpClient
from engramdb.types import Memory, MemoryVersion, SearchResult
from engramdb.embeddings import DummyEmbedding, OpenAIEmbedding
from engramdb.memory_manager import (
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
