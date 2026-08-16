"""Check data with known user ID and diagnose pgvector."""
import httpx
import json

c = httpx.Client(base_url="http://localhost:8100/api/v1", timeout=10)

# Use the user ID from the last seed run
user_id = None

# Try to find users by listing memories (no GET /users endpoint)
# Let's check the deep health first
print("=== Deep Health ===")
r = c.get("/health/deep")
print(json.dumps(r.json(), indent=2))

# Try to get memories - we need to try the user IDs from our seed runs
for uid in ["5266f648-5739-4a10-b360-5a00e5a7204a", "18d91135-1873-4512-adc7-b2fb3fdc65c7"]:
    r = c.get("/memories", params={"user_id": uid})
    if r.status_code == 200:
        mems = r.json()
        if mems:
            print(f"\nFound {len(mems)} memories for user {uid}")
            user_id = uid
            for m in mems:
                print(f"  [{m['memory_type']}] {m['memory_key']}: {m['content'][:60]}")
            break

if not user_id:
    # Try to find any memories
    print("\nTrying to search without user filter...")

# Test search
if user_id:
    print(f"\n=== Search Test (user={user_id}) ===")
    r = c.post("/memories/search", json={
        "user_id": user_id,
        "query": "What does the user like?",
        "top_k": 5
    })
    print(f"Status: {r.status_code}")
    data = r.json()
    print(f"Results: {data.get('total_candidates', '?')} candidates")
    for item in data.get("results", []):
        mem = item["memory"]
        print(f"  {mem['memory_key']}: {mem['content'][:50]}")
