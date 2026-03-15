#!/usr/bin/env python3
"""Demo: Event → Observation → Memory pipeline.

Walks through the core agentic-memory flow:
1. Create a user and a run.
2. Post an event (e.g. user_input).
3. Extract an observation from that event.
4. Upsert the observation content as a semantic memory.
5. Verify the memory was persisted.

Prerequisites:
    docker compose up -d
    # wait for health-check at http://localhost:8100/api/v1/health

Usage:
    python examples/scripts/demo_event_to_memory.py
"""

from __future__ import annotations

import httpx
import uuid
import sys

BASE = "http://localhost:8100/api/v1"


def main() -> None:
    client = httpx.Client(base_url=BASE, timeout=10)

    # 1. Health check
    r = client.get("/health")
    r.raise_for_status()
    print("✓ API is healthy:", r.json())

    # 2. Create a user
    user_id = str(uuid.uuid4())
    r = client.post("/users", json={"id": user_id, "name": "demo-user"})
    r.raise_for_status()
    user = r.json()
    print(f"✓ Created user: {user['id']}")

    # 3. Create an agent run
    r = client.post(
        "/runs",
        json={
            "user_id": user_id,
            "agent_name": "demo-agent",
            "status": "running",
        },
    )
    r.raise_for_status()
    run = r.json()
    run_id = run["id"]
    print(f"✓ Created run: {run_id}")

    # 4. Post an event
    r = client.post(
        "/events",
        json={
            "run_id": run_id,
            "user_id": user_id,
            "event_type": "user_input",
            "content": "My favourite programming language is Python.",
            "source": "demo-script",
        },
    )
    r.raise_for_status()
    event = r.json()
    event_id = event["id"]
    print(f"✓ Created event: {event_id}")

    # 5. Extract an observation
    r = client.post(
        "/observations/extract-from-event",
        json={"event_id": event_id},
    )
    r.raise_for_status()
    observations = r.json()
    print(f"✓ Extracted {len(observations)} observation(s)")

    if not observations:
        print("  (No extractable observations — try a different event type.)")
    else:
        obs = observations[0]
        print(f"  Observation: {obs['content'][:80]}…")

    # 6. Upsert as memory
    r = client.post(
        "/memories/upsert",
        json={
            "user_id": user_id,
            "memory_key": "user:fav_language",
            "memory_type": "semantic",
            "content": "The user's favourite programming language is Python.",
            "source_type": "tool",
            "source_event_id": event_id,
            "importance_score": 0.75,
        },
    )
    r.raise_for_status()
    memory = r.json()
    print(f"✓ Upserted memory: {memory['id']}  (version={memory['version']})")

    # 7. Read it back
    r = client.get(f"/memories/{memory['id']}")
    r.raise_for_status()
    fetched = r.json()
    print(f"✓ Fetched memory content: {fetched['content'][:80]}")

    print("\n🎉 Event → Observation → Memory pipeline complete.")


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPStatusError as exc:
        print(f"HTTP {exc.response.status_code}: {exc.response.text}", file=sys.stderr)
        sys.exit(1)
