"""Check what data exists in the backend."""
import httpx
import json

c = httpx.Client(base_url="http://localhost:8100/api/v1", timeout=10)

# Check version endpoint
print("=== /version ===")
r = c.get("/version")
print(r.status_code, r.text[:200])

# Check deep health
print("\n=== /health/deep ===")
r = c.get("/health/deep")
print(r.status_code, r.text[:300])

# List users
print("\n=== /users ===")
r = c.get("/users")
print(r.status_code, r.text[:300])

# List memories for each user
users = r.json()
for u in users:
    uid = u["id"]
    r = c.get("/memories", params={"user_id": uid})
    mems = r.json()
    print(f"\nUser: {u['name']} ({uid})")
    print(f"  Memories: {len(mems)}")
    for m in mems:
        mt = m["memory_type"]
        mk = m["memory_key"]
        ct = m["content"][:50]
        print(f"    [{mt}] {mk}: {ct}")

# Scheduler
print("\n=== /scheduler/status ===")
r = c.get("/scheduler/status")
print(r.status_code, r.text[:400])
