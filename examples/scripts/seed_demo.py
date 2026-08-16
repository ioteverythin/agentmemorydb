"""Seed demo data for the Explorer UI."""
import httpx
import uuid

BASE = "http://localhost:8100/api/v1"
client = httpx.Client(base_url=BASE, timeout=10)

# Health check
r = client.get("/health")
r.raise_for_status()
print("API healthy:", r.json())

# Create user
r = client.post("/users", json={"name": "demo-user"})
r.raise_for_status()
user_data = r.json()
user_id = user_data["id"]
print(f"Created user: {user_id}")
print(f"  User response: {user_data}")

# Create run
r = client.post("/runs", json={"user_id": user_id, "agent_name": "demo-agent", "status": "running"})
r.raise_for_status()
run_id = r.json()["id"]
print(f"Created run: {run_id}")

# Post events
events = [
    {"event_type": "user_input", "content": "My favourite programming language is Python.", "source": "demo"},
    {"event_type": "tool_call", "content": "Called weather API for Tokyo forecast.", "source": "weather-tool"},
    {"event_type": "model_output", "content": "Based on your preferences, I recommend trying ramen in Shibuya.", "source": "gpt-4"},
]
event_ids = []
for e in events:
    r = client.post("/events", json={"run_id": run_id, "user_id": user_id, **e})
    r.raise_for_status()
    event_ids.append(r.json()["id"])
print(f"Created {len(event_ids)} events")

# Seed memories
memories = [
    {"memory_key": "pref:language", "memory_type": "semantic", "content": "The user prefers Python for programming.", "importance_score": 0.8},
    {"memory_key": "pref:color", "memory_type": "semantic", "content": "The user prefers the colour blue.", "importance_score": 0.6},
    {"memory_key": "pref:food", "memory_type": "semantic", "content": "The user loves sushi and Japanese food.", "importance_score": 0.7},
    {"memory_key": "fact:capital", "memory_type": "semantic", "content": "The capital of Japan is Tokyo.", "importance_score": 0.4},
    {"memory_key": "episode:meeting", "memory_type": "episodic", "content": "User had a meeting with the design team on Monday.", "importance_score": 0.5},
    {"memory_key": "pref:music", "memory_type": "semantic", "content": "The user enjoys jazz and lo-fi music.", "importance_score": 0.55},
    {"memory_key": "pref:framework", "memory_type": "semantic", "content": "The user likes FastAPI and React for web development.", "importance_score": 0.75},
    {"memory_key": "episode:travel", "memory_type": "episodic", "content": "User went to Tokyo last summer for a conference.", "importance_score": 0.6},
    {"memory_key": "proc:deploy", "memory_type": "procedural", "content": "To deploy, run docker compose up -d and then alembic upgrade head.", "importance_score": 0.65},
    {"memory_key": "work:todo", "memory_type": "working", "content": "Currently investigating memory consolidation performance.", "importance_score": 0.5},
]
for m in memories:
    r = client.post("/memories/upsert", json={"user_id": user_id, **m})
    r.raise_for_status()
print(f"Seeded {len(memories)} memories")

# Search test
r = client.post("/memories/search", json={"user_id": user_id, "query": "What programming language does the user prefer?", "top_k": 5})
r.raise_for_status()
search = r.json()
tc = search["total_candidates"]
print(f"\nSearch results ({tc} candidates):")
for i, item in enumerate(search["results"], 1):
    mem = item["memory"]
    score = item.get("score") or item.get("final_score") or 0
    print(f"  #{i} [{mem['memory_type']}] {mem['memory_key']}: {mem['content'][:60]}  (score={score})")

# Create a task
r = client.post("/tasks", json={"user_id": user_id, "run_id": run_id, "title": "Review memory pipeline", "description": "Verify event-to-memory flow works end to end", "state": "pending", "priority": 2})
r.raise_for_status()
task_id = r.json()["id"]
print(f"\nCreated task: {task_id}")

# Transition task
try:
    r = client.patch(f"/tasks/{task_id}/transition", json={"new_state": "in_progress", "reason": "Starting review", "triggered_by": "demo"})
    r.raise_for_status()
    print("Task transitioned to in_progress")
except Exception as e:
    # Try alternate schema
    try:
        r = client.patch(f"/tasks/{task_id}/transition", json={"state": "in_progress", "reason": "Starting review", "triggered_by": "demo"})
        r.raise_for_status()
        print("Task transitioned to in_progress")
    except Exception as e2:
        print(f"  Task transition skipped: {e2}")

# Create memory links
r = client.get(f"/memories?user_id={user_id}")
r.raise_for_status()
all_mems = r.json()
if len(all_mems) >= 3:
    links = [
        {"source": 0, "target": 1, "link_type": "related_to", "reason": "both are user preferences"},
        {"source": 1, "target": 2, "link_type": "supports", "reason": "complementary info"},
        {"source": 0, "target": 2, "link_type": "derived_from", "reason": "derived context"},
        {"source": 3, "target": 7, "link_type": "related_to", "reason": "both about Japan/Tokyo"},
        {"source": 6, "target": 0, "link_type": "supports", "reason": "framework supports language pref"},
    ]
    for link in links:
        if link["source"] < len(all_mems) and link["target"] < len(all_mems):
            r = client.post("/memory-links", json={
                "source_memory_id": all_mems[link["source"]]["id"],
                "target_memory_id": all_mems[link["target"]]["id"],
                "link_type": link["link_type"],
                "metadata": {"reason": link["reason"]},
            })
            r.raise_for_status()
    print(f"Created {len(links)} memory links")

print(f"\n{'='*50}")
print(f"  USER ID: {user_id}")
print(f"{'='*50}")
print("Paste this user ID in the Explorer UI to search and browse.")
print("Done!")
