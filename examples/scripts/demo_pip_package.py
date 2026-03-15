#!/usr/bin/env python3
"""
AgentMemoryDB — Live Demo Script
=================================

Demonstrates the pip package with:
  • HuggingFace sentence-transformers embeddings (semantic search)
  • OpenAI embeddings (if OPENAI_API_KEY is set)
  • Fallback DummyEmbedding (hash-based, always works)
  • Full CRUD, versioning, PII masking, multi-user isolation

Usage
-----
  # Install deps first:
  pip install sentence-transformers numpy

  # Run with HuggingFace (default):
  python examples/scripts/demo_pip_package.py

  # Run with OpenAI:
  set OPENAI_API_KEY=sk-...
  python examples/scripts/demo_pip_package.py --provider openai

  # Run with dummy (no extra deps):
  python examples/scripts/demo_pip_package.py --provider dummy
"""

from __future__ import annotations

import argparse
import os
import sys
import time

# ── Make sure the local agentmemodb package is importable ──
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import agentmemodb
from agentmemodb.embeddings import DummyEmbedding, EmbeddingFunction, OpenAIEmbedding


# ═══════════════════════════════════════════════════════════════════
#  HuggingFace Sentence-Transformers Embedding Provider
# ═══════════════════════════════════════════════════════════════════

class HuggingFaceEmbedding:
    """Sentence-Transformers embedding provider.

    Works with any model on HuggingFace Hub, e.g.:
      - all-MiniLM-L6-v2        (384-d, fast, English)
      - all-mpnet-base-v2       (768-d, better quality)
      - paraphrase-multilingual-MiniLM-L12-v2  (384-d, 50+ languages)
      - BAAI/bge-small-en-v1.5  (384-d, top-ranked)
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for HuggingFace embeddings.\n"
                "Install with:  pip install sentence-transformers"
            ) from None

        print(f"  Loading model '{model_name}' ...")
        t0 = time.time()
        self._model = SentenceTransformer(model_name)
        self._dimension = self._model.get_sentence_embedding_dimension()
        print(f"  Model loaded in {time.time() - t0:.1f}s  (dimension={self._dimension})")

    @property
    def dimension(self) -> int:
        return self._dimension

    def __call__(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return [e.tolist() for e in embeddings]


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════

def divider(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def print_results(results: list[agentmemodb.SearchResult], label: str = "Search Results") -> None:
    print(f"\n  {label}  ({len(results)} hits)")
    for i, r in enumerate(results, 1):
        print(f"    {i}. [{r.score:.4f}]  {r.key}  →  {r.content}")


def build_embedding(provider: str, model_name: str | None) -> EmbeddingFunction:
    """Build the requested embedding provider."""
    if provider == "huggingface":
        return HuggingFaceEmbedding(model_name or "all-MiniLM-L6-v2")
    elif provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("  ⚠  OPENAI_API_KEY not set — falling back to DummyEmbedding")
            return DummyEmbedding()
        return OpenAIEmbedding(api_key=api_key)
    else:
        return DummyEmbedding()


# ═══════════════════════════════════════════════════════════════════
#  Demo Sections
# ═══════════════════════════════════════════════════════════════════

def demo_basic_crud(db: agentmemodb.Client) -> None:
    """Basic upsert, get, list, count, delete."""
    divider("1 · Basic CRUD")

    # Upsert several memories
    memories_data = [
        ("user-alice", "pref:language",   "Alice prefers Python for backend development"),
        ("user-alice", "pref:editor",     "Alice uses VS Code with Copilot"),
        ("user-alice", "pref:framework",  "Alice builds APIs with FastAPI"),
        ("user-alice", "pref:database",   "Alice uses PostgreSQL with pgvector for AI workloads"),
        ("user-alice", "pref:cloud",      "Alice deploys on AWS using ECS Fargate"),
        ("user-alice", "skill:ml",        "Alice is experienced with PyTorch and HuggingFace transformers"),
        ("user-alice", "project:current", "Alice is building an AI agent memory system"),
    ]

    for uid, key, content in memories_data:
        mem = db.upsert(uid, key, content)
        print(f"  ✓ upsert  {key}  (id={mem.id[:8]}…  v{mem.version})")

    # Count
    n = db.count("user-alice")
    print(f"\n  Total memories for user-alice: {n}")

    # Get by key
    mem = db.get("user-alice", "pref:language")
    if mem:
        print(f"\n  Get 'pref:language':  {mem.content}")

    # List with filter
    all_prefs = db.list("user-alice", memory_type="semantic")
    print(f"  List (semantic):  {len(all_prefs)} memories")


def demo_semantic_search(db: agentmemodb.Client) -> None:
    """Show semantic search in action."""
    divider("2 · Semantic Search")

    queries = [
        "What programming language does Alice like?",
        "Which cloud provider does she use?",
        "Tell me about her machine learning experience",
        "What database technology?",
        "What project is she working on?",
    ]

    for q in queries:
        results = db.search("user-alice", q, top_k=3)
        print(f"\n  Q: \"{q}\"")
        for i, r in enumerate(results, 1):
            print(f"     {i}. [{r.score:.4f}]  {r.key}  →  {r.content}")


def demo_versioning(db: agentmemodb.Client) -> None:
    """Show content-hash dedup and versioning."""
    divider("3 · Versioning & Deduplication")

    # First write
    m1 = db.upsert("user-alice", "pref:language", "Alice prefers Python for backend development")
    print(f"  Write 1 (same content):   v{m1.version}  — no version bump (content-hash dedup)")

    # Update with new content
    m2 = db.upsert("user-alice", "pref:language", "Alice now prefers Rust for systems programming")
    print(f"  Write 2 (new content):    v{m2.version}  — new version!")

    m3 = db.upsert("user-alice", "pref:language", "Alice uses both Python and Rust depending on the project")
    print(f"  Write 3 (another update): v{m3.version}")

    # Fetch version history
    versions = db.versions(m3.id)
    print(f"\n  Version history ({len(versions)} snapshots):")
    for v in versions:
        print(f"    v{v.version}: {v.content}")

    # Current value
    current = db.get("user-alice", "pref:language")
    if current:
        print(f"\n  Current value: v{current.version} → {current.content}")


def demo_multi_user(db: agentmemodb.Client) -> None:
    """Show user isolation."""
    divider("4 · Multi-User Isolation")

    db.upsert("user-bob", "pref:language", "Bob loves JavaScript and TypeScript")
    db.upsert("user-bob", "pref:editor", "Bob uses WebStorm")
    db.upsert("user-bob", "pref:framework", "Bob builds with Next.js and React")

    # Search as Alice — should NOT see Bob's data
    alice_results = db.search("user-alice", "What language?", top_k=3)
    bob_results = db.search("user-bob", "What language?", top_k=3)

    print("\n  Alice's results (searching 'What language?'):")
    for r in alice_results:
        print(f"    [{r.score:.4f}]  {r.content}")

    print("\n  Bob's results (searching 'What language?'):")
    for r in bob_results:
        print(f"    [{r.score:.4f}]  {r.content}")

    print(f"\n  ✓ Alice has {db.count('user-alice')} memories, Bob has {db.count('user-bob')} memories")
    print(f"  ✓ Data is fully isolated between users")


def demo_memory_types(db: agentmemodb.Client) -> None:
    """Show different memory types and filtering."""
    divider("5 · Memory Types & Scopes")

    # Episodic memories (specific events)
    db.upsert("user-alice", "episode:debug-session",
              "Alice spent 3 hours debugging a race condition in asyncio",
              memory_type="episodic", importance=0.7)

    db.upsert("user-alice", "episode:conference",
              "Alice gave a talk on vector databases at PyCon 2025",
              memory_type="episodic", importance=0.9)

    # Procedural memories (how-to knowledge)
    db.upsert("user-alice", "howto:deploy",
              "To deploy: run make docker-build, push to ECR, update ECS service",
              memory_type="procedural")

    db.upsert("user-alice", "howto:test",
              "Run pytest tests/unit -v for unit tests, use --tb=short for brief output",
              memory_type="procedural")

    # Search only episodic
    print("\n  Episodic memories only:")
    results = db.search("user-alice", "What happened recently?",
                        top_k=3, memory_types=["episodic"])
    for r in results:
        print(f"    [{r.score:.4f}]  {r.key}  →  {r.content}")

    # Search only procedural
    print("\n  Procedural memories only:")
    results = db.search("user-alice", "How do I deploy?",
                        top_k=3, memory_types=["procedural"])
    for r in results:
        print(f"    [{r.score:.4f}]  {r.key}  →  {r.content}")

    # All types
    total = db.count("user-alice")
    print(f"\n  Total memories across all types: {total}")


def demo_metadata(db: agentmemodb.Client) -> None:
    """Show metadata storage and retrieval."""
    divider("6 · Rich Metadata")

    db.upsert(
        "user-alice", "tool:github-copilot",
        "Alice uses GitHub Copilot for code completion and chat",
        metadata={
            "source": "user_survey",
            "tags": ["tools", "ai", "productivity"],
            "satisfaction_score": 9.2,
            "since": "2024-01",
        },
        importance=0.8,
        confidence=0.95,
        authority=8.0,
    )

    mem = db.get("user-alice", "tool:github-copilot")
    if mem:
        print(f"  Key:        {mem.key}")
        print(f"  Content:    {mem.content}")
        print(f"  Type:       {mem.memory_type}")
        print(f"  Importance: {mem.importance}")
        print(f"  Confidence: {mem.confidence}")
        print(f"  Authority:  {mem.authority}")
        print(f"  Metadata:   {mem.metadata}")
        print(f"  Version:    {mem.version}")
        print(f"  Hash:       {mem.content_hash[:16]}…")


def demo_pii_masking(db_clean: agentmemodb.Client) -> None:
    """Show PII masking in action (separate client with mask_pii=True)."""
    divider("7 · PII Masking")

    print("  Creating a separate client with mask_pii=True ...\n")

    # We create a separate in-memory client with PII masking enabled
    with agentmemodb.Client(path=":memory:", mask_pii=True) as masked_db:
        # Store content with PII
        raw_text = "Contact Josh at josh.miller@company.com or call +1-555-867-5309. SSN: 123-45-6789"
        print(f"  Input:   {raw_text}")

        mem = masked_db.upsert("user-test", "contact:josh", raw_text)
        print(f"  Stored:  {mem.content}")
        print()

        # More PII examples
        examples = [
            ("payment:info", "Credit card 4111-1111-1111-1111, IP 192.168.1.100"),
            ("personal:dob", "Date of birth: 03/15/1990, passport A12345678"),
            ("safe:content", "This text has no PII at all — just normal discussion"),
        ]

        for key, text in examples:
            m = masked_db.upsert("user-test", key, text)
            print(f"  [{key}]")
            print(f"    In:  {text}")
            print(f"    Out: {m.content}")


def demo_delete_and_count(db: agentmemodb.Client) -> None:
    """Show delete operations."""
    divider("8 · Delete & Cleanup")

    before = db.count("user-bob")
    print(f"  Bob's memories before: {before}")

    deleted = db.delete("user-bob", "pref:editor")
    print(f"  Deleted 'pref:editor': {deleted}")

    after = db.count("user-bob")
    print(f"  Bob's memories after:  {after}")

    # Try deleting non-existent
    gone = db.delete("user-bob", "nonexistent:key")
    print(f"  Delete nonexistent:    {gone}")


def demo_scale_test(db: agentmemodb.Client) -> None:
    """Quick scale test — insert many memories and search."""
    divider("9 · Scale Test (500 memories)")

    t0 = time.time()
    for i in range(500):
        db.upsert(
            "user-scale",
            f"fact:{i:04d}",
            f"This is fact number {i} about topic {i % 10}",
            importance=round((i % 10) / 10, 1),
        )
    insert_time = time.time() - t0
    print(f"  Inserted 500 memories in {insert_time:.2f}s  ({500/insert_time:.0f} ops/sec)")

    t0 = time.time()
    results = db.search("user-scale", "topic 7", top_k=5)
    search_time = time.time() - t0
    print(f"  Search took {search_time*1000:.1f}ms")
    print_results(results, "Top 5 for 'topic 7'")

    count = db.count("user-scale")
    print(f"\n  Total: {count} memories")


def demo_context_manager(db: agentmemodb.Client) -> None:
    """Show context manager pattern."""
    divider("10 · Context Manager Pattern")

    print("  with agentmemodb.Client(path=':memory:') as tmp:")
    with agentmemodb.Client(path=":memory:") as tmp:
        tmp.upsert("u1", "greeting", "Hello from a context-managed client!")
        mem = tmp.get("u1", "greeting")
        print(f"    → {mem.content}")
        print(f"    → Client auto-closes when exiting 'with' block")
    print("  ✓ Done (connection closed)")


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AgentMemoryDB — Pip Package Live Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python demo_pip_package.py                           # HuggingFace (default)
  python demo_pip_package.py --provider openai         # OpenAI embeddings
  python demo_pip_package.py --provider dummy          # Hash-based (no deps)
  python demo_pip_package.py --provider huggingface --model BAAI/bge-small-en-v1.5
        """,
    )
    parser.add_argument(
        "--provider", choices=["huggingface", "openai", "dummy"],
        default="huggingface",
        help="Embedding provider (default: huggingface)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="HuggingFace model name (default: all-MiniLM-L6-v2)",
    )
    args = parser.parse_args()

    # ── Banner ──
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       AgentMemoryDB — Pip Package Live Demo             ║")
    print(f"║       Version {agentmemodb.__version__}                                    ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    # ── Build embedding provider ──
    print(f"  Provider: {args.provider}")
    embed_fn = build_embedding(args.provider, args.model)
    print(f"  Dimension: {embed_fn.dimension}")

    # ── Create in-memory client ──
    db = agentmemodb.Client(path=":memory:", embedding_fn=embed_fn)
    print(f"  Client: {db}")
    print(f"  Storage: in-memory SQLite (no files on disk)")

    try:
        demo_basic_crud(db)
        demo_semantic_search(db)
        demo_versioning(db)
        demo_multi_user(db)
        demo_memory_types(db)
        demo_metadata(db)
        demo_pii_masking(db)
        demo_delete_and_count(db)
        demo_scale_test(db)
        demo_context_manager(db)

        # ── Summary ──
        divider("Summary")
        print(f"  Provider:         {args.provider} ({type(embed_fn).__name__})")
        print(f"  Dimension:        {embed_fn.dimension}")
        print(f"  Alice's memories: {db.count('user-alice')}")
        print(f"  Bob's memories:   {db.count('user-bob')}")
        print(f"  Scale memories:   {db.count('user-scale')}")
        print(f"  Total:            {db.count('user-alice') + db.count('user-bob') + db.count('user-scale')}")
        print()
        print("  ✅ All demos completed successfully!")
        print()

    finally:
        db.close()


if __name__ == "__main__":
    main()
