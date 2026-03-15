"""
Simplest possible AgentMemoryDB demo.
No server, no Docker, no UUIDs — just works.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agentmemodb

# ── Zero config: in-memory SQLite, no server needed ──────────
db = agentmemodb.Client(":memory:")

print("Storing memories...")
db.upsert("josh", "pref:food",  "User loves sushi and Japanese food")
db.upsert("josh", "pref:lang",  "User prefers Python for programming")
db.upsert("josh", "pref:music", "User enjoys jazz and lo-fi music")
db.upsert("josh", "fact:pet",   "User has a golden retriever named Max")
db.upsert("josh", "fact:city",  "User lives in San Francisco")
db.upsert("josh", "goal:work",  "User wants to build an AI startup")
print(f"  Stored {db.count('josh')} memories\n")

# ── Search ────────────────────────────────────────────────────
queries = [
    "what food does the user like?",
    "programming language preference",
    "where does the user live?",
    "what are the user's goals?",
]

for q in queries:
    print(f"Q: {q}")
    results = db.search("josh", q, top_k=2)
    for r in results:
        print(f"  → [{r.score:.3f}] {r.memory.content}")
    print()

db.close()
print("NOTE: scores above use DummyEmbedding (hash-based, not semantic).")
print("For real semantic search, install: pip install sentence-transformers")
print("Then pass: agentmemodb.Client(embedding_fn=HuggingFaceEmbedding())")
