#!/usr/bin/env python3
"""Demo: Memory search with hybrid scoring.

Shows how to:
1. Seed several memories.
2. Perform a hybrid search (metadata path when no pgvector).
3. Inspect the score breakdown for each result.

Prerequisites:
    docker compose up -d

Usage:
    python examples/scripts/demo_memory_search.py
"""

from __future__ import annotations

import httpx
import uuid
import sys

BASE = "http://localhost:8100/api/v1"


def main() -> None:
    client = httpx.Client(base_url=BASE, timeout=10)

    # 1. Create user
    user_id = str(uuid.uuid4())
    client.post("/users", json={"id": user_id, "name": "search-demo-user"}).raise_for_status()
    print(f"✓ User {user_id[:8]}…")

    # 2. Seed memories
    memories_to_create = [
        {
            "memory_key": "pref:color",
            "memory_type": "semantic",
            "content": "The user prefers the colour blue.",
            "importance_score": 0.6,
        },
        {
            "memory_key": "pref:food",
            "memory_type": "semantic",
            "content": "The user's favourite food is sushi.",
            "importance_score": 0.7,
        },
        {
            "memory_key": "fact:capital",
            "memory_type": "semantic",
            "content": "The capital of Japan is Tokyo.",
            "importance_score": 0.4,
        },
        {
            "memory_key": "episode:meeting",
            "memory_type": "episodic",
            "content": "User had a meeting with the design team on Monday.",
            "importance_score": 0.5,
        },
        {
            "memory_key": "pref:music",
            "memory_type": "semantic",
            "content": "The user enjoys jazz music.",
            "importance_score": 0.55,
        },
    ]
    for m in memories_to_create:
        r = client.post(
            "/memories/upsert",
            json={"user_id": user_id, **m},
        )
        r.raise_for_status()
    print(f"✓ Seeded {len(memories_to_create)} memories")

    # 3. Search
    r = client.post(
        "/memories/search",
        json={
            "user_id": user_id,
            "query": "What does the user like to eat?",
            "top_k": 3,
        },
    )
    r.raise_for_status()
    search = r.json()

    print(f"\n🔍 Search results ({search['total_candidates']} candidates):\n")
    for i, item in enumerate(search["results"], 1):
        mem = item["memory"]
        score = item["score_breakdown"]
        print(f"  #{i}  key={mem['memory_key']}")
        print(f"      content: {mem['content'][:60]}")
        print(f"      final_score: {item['final_score']:.4f}")
        print(f"      breakdown: vector={score['vector_similarity']:.3f}  "
              f"recency={score['recency']:.3f}  importance={score['importance']:.3f}  "
              f"authority={score['authority']:.3f}  confidence={score['confidence']:.3f}")
        print()

    # 4. Filter by type
    r = client.get(f"/memories?user_id={user_id}&memory_type=episodic")
    r.raise_for_status()
    episodic = r.json()
    print(f"📋 Episodic memories: {len(episodic)}")
    for m in episodic:
        print(f"   • {m['memory_key']}: {m['content'][:50]}")

    print("\n🎉 Memory search demo complete.")


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPStatusError as exc:
        print(f"HTTP {exc.response.status_code}: {exc.response.text}", file=sys.stderr)
        sys.exit(1)
