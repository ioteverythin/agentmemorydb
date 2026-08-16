import requests, json

r = requests.post(
    "http://localhost:8100/api/v1/graph/expand",
    json={"seed_memory_id": "bc458192-c4b2-487e-807b-afcfd199c5ad", "max_hops": 3, "max_nodes": 80},
)
print(r.status_code)
d = r.json()
print(f"Nodes: {d['total_nodes']}")
for n in d["nodes"]:
    print(f"  depth={n['depth']} {n['memory_key']}: {n['content'][:50]}")
