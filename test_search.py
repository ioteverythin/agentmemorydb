import requests
import json

user_id = "70758e2d-7437-4ffa-bf0a-1c25c2e547ee"
r = requests.post(
    "http://localhost:8100/api/v1/memories/search",
    json={"user_id": user_id, "query_text": "What does the user like?", "top_k": 5},
)
data = r.json()
print(f"Strategy: {data['strategy']}, Candidates: {data['total_candidates']}")
for x in data["results"]:
    m = x["memory"]
    print(f"  [{m['memory_type']}] {m['memory_key']}: {m['content'][:70]}")
