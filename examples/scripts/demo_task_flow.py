#!/usr/bin/env python3
"""Demo: Task lifecycle with state machine transitions.

Demonstrates the task state machine:
    pending → in_progress → completed

Also shows an invalid transition being rejected.

Prerequisites:
    docker compose up -d

Usage:
    python examples/scripts/demo_task_flow.py
"""

from __future__ import annotations

import httpx
import uuid
import sys

BASE = "http://localhost:8100/api/v1"


def main() -> None:
    client = httpx.Client(base_url=BASE, timeout=10)

    # 1. Create user + run
    user_id = str(uuid.uuid4())
    client.post("/users", json={"id": user_id, "name": "task-demo-user"}).raise_for_status()

    r = client.post(
        "/runs",
        json={"user_id": user_id, "agent_name": "task-agent", "status": "running"},
    )
    r.raise_for_status()
    run_id = r.json()["id"]
    print(f"✓ User + Run created ({run_id[:8]}…)")

    # 2. Create a task
    r = client.post(
        "/tasks",
        json={
            "run_id": run_id,
            "user_id": user_id,
            "title": "Summarise quarterly report",
            "description": "Read the Q3 report PDF and produce a 200-word summary.",
            "priority": 2,
        },
    )
    r.raise_for_status()
    task = r.json()
    task_id = task["id"]
    print(f"✓ Task created: {task_id[:8]}…  state={task['state']}")

    # 3. Transition: pending → in_progress
    r = client.patch(
        f"/tasks/{task_id}/transition",
        json={
            "to_state": "in_progress",
            "reason": "Agent picked up the task.",
            "triggered_by": "scheduler",
        },
    )
    r.raise_for_status()
    task = r.json()
    print(f"✓ Transitioned → {task['state']}")

    # 4. Transition: in_progress → completed
    r = client.patch(
        f"/tasks/{task_id}/transition",
        json={
            "to_state": "completed",
            "reason": "Summary generated successfully.",
            "triggered_by": "agent",
        },
    )
    r.raise_for_status()
    task = r.json()
    print(f"✓ Transitioned → {task['state']}")

    # 5. Attempt invalid transition: completed → in_progress  (should fail)
    print("\n⚡ Attempting invalid transition: completed → in_progress")
    r = client.patch(
        f"/tasks/{task_id}/transition",
        json={
            "to_state": "in_progress",
            "reason": "Trying to go back.",
            "triggered_by": "user",
        },
    )
    if r.status_code == 409:
        err = r.json()
        print(f"✓ Correctly rejected (409): {err.get('detail', err)}")
    else:
        print(f"✗ Unexpected status {r.status_code}: {r.text}")

    # 6. Re-read task to confirm final state
    r = client.get(f"/tasks/{task_id}")
    r.raise_for_status()
    final = r.json()
    print(f"\n📋 Final task state: {final['state']}")

    # 7. Create a second task and cancel it
    r = client.post(
        "/tasks",
        json={
            "run_id": run_id,
            "user_id": user_id,
            "title": "Cancelled task example",
            "description": "This task will be cancelled before starting.",
        },
    )
    r.raise_for_status()
    t2_id = r.json()["id"]

    r = client.patch(
        f"/tasks/{t2_id}/transition",
        json={
            "to_state": "cancelled",
            "reason": "No longer needed.",
            "triggered_by": "user",
        },
    )
    r.raise_for_status()
    print(f"✓ Second task cancelled: {t2_id[:8]}…  state={r.json()['state']}")

    # 8. List all tasks for the run
    r = client.get(f"/tasks?user_id={user_id}")
    r.raise_for_status()
    tasks = r.json()
    print(f"\n📋 Tasks for user ({len(tasks)}):")
    for t in tasks:
        print(f"   • [{t['state']:12s}] {t['title']}")

    print("\n🎉 Task flow demo complete.")


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPStatusError as exc:
        print(f"HTTP {exc.response.status_code}: {exc.response.text}", file=sys.stderr)
        sys.exit(1)
