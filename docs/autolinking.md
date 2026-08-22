# Automatic Memory Linking

EngramDB has had a typed memory graph from the start — `supersedes` from
bitemporal supersession, `contradicts` from conflict resolution, `derived_from`
from reflection. Every one of those edges is written by a process that *knows*
the relationship, because it created it.

Nothing writes the plain "these two are about the same thing" edge. So in
practice the graph stays sparse: `/graph/expand` from a memory reaches only what
somebody explicitly linked, which is almost nothing. The graph exists and is
empty.

Autolinking fills it in. When a memory is written, its nearest topical
neighbours get a `related_to` edge, and traversal from any memory reaches its
neighbourhood without an agent ever reasoning about which links to create.

---

## What it does

```
write "Runs migrations nightly"
        │
        ├─ nearest neighbours, same owner, same project, above the threshold
        │       "Uses Postgres for analytics"     0.91  ──▶ related_to
        │       "Asked about connection pooling"  0.88  ──▶ related_to
        │       "Prefers dark mode"               0.31  ──▶ (below bar, skipped)
        │
        └─ capped at AUTOLINK_MAX_LINKS
```

Three constraints keep it from degrading into noise.

**A high bar and a low cap.** Only pairs above
`AUTOLINK_SIMILARITY_THRESHOLD` (default 0.85), at most `AUTOLINK_MAX_LINKS`
(default 3) per write. A generous threshold connects everything to everything,
which conveys exactly as much as connecting nothing.

**Undirected deduplication.** `related_to` is symmetric — A→B and B→A are the
same claim — so only one direction is stored and an existing edge in *either*
direction suppresses a new one. Without this, every re-write of either memory
would add another copy of the same relationship, and a frequently-updated memory
would accumulate hundreds of identical edges.

**Nothing untrustworthy is linked.** Quarantined, disputed, and retracted
memories are neither sources nor targets. An edge from a trusted memory into a
quarantined one is a path an agent can traverse — which would route straight
around the quarantine that held it back. See
[`docs/provenance.md`](provenance.md).

Autolinking also never crosses users, and never crosses projects: two projects
deliberately kept apart must not be bridged by an inference about similarity.

---

## Turning it on

```bash
ENABLE_AUTOLINK=true
```

That governs linking **on write**. An established store stays as sparse as it
was, because nothing re-writes its existing memories — so there is a backfill:

```bash
# What would be linked (default: dry run, writes nothing)
curl -X POST 'localhost:8100/api/v1/graph/autolink-backfill?user_id={id}'

# Actually link
curl -X POST 'localhost:8100/api/v1/graph/autolink-backfill?user_id={id}&dry_run=false'

# Or one memory at a time
curl -X POST 'localhost:8100/api/v1/memories/{id}/autolink'
```

Both endpoints run on explicit request whether or not the flag is on — the flag
governs the automatic behaviour, and someone calling the endpoint has already
decided. Both are safe to re-run: deduplication means a second pass adds nothing.

Then traverse:

```bash
curl -X POST localhost:8100/api/v1/graph/expand \
  -H 'Content-Type: application/json' \
  -d '{"seed_memory_id":"…","max_hops":2,"link_types":["related_to"]}'
```

---

## Cost

One extra query per write (the candidate scan, capped at
`AUTOLINK_CANDIDATE_POOL` rows) plus one for existing-edge lookup, with the
similarity itself computed in Python over vectors already in memory. Two
composite indexes on `memory_links (link_type, source_memory_id)` and
`(link_type, target_memory_id)` keep the dedup lookup index-only in both
directions.

Linking is enrichment, not part of the write's contract: a failure inside
autolinking is logged and swallowed rather than failing the upsert that
triggered it. A memory that could not be linked is still a memory.

---

## Observability

```
engramdb_autolinks_total
```

Counts `related_to` edges created automatically. Flat while the feature is off;
a sudden spike after a threshold change is the signal that the bar is now too
low.

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_AUTOLINK` | `false` | Link on write |
| `AUTOLINK_SIMILARITY_THRESHOLD` | `0.85` | Cosine similarity required to link |
| `AUTOLINK_MAX_LINKS` | `3` | Maximum new edges per write |
| `AUTOLINK_CANDIDATE_POOL` | `100` | Recent memories scanned per write |

---

## Design notes

**Why not a unique constraint on (source, target, type)?** Existing deployments
may already hold duplicate manual links, and a migration that fails on real data
is worse than one that leaves deduplication to the writer. The composite indexes
make the writer's check cheap instead.

**Why `related_to` rather than a new link type?** It already exists in
`LinkType`, it already means what this means, and graph traversal already
understands it. A separate `auto_related` type would fragment the graph and force
every consumer to know about both.

**Why the description records the similarity.** `autolinked (similarity 0.912)`
in the edge's description makes it possible to audit a threshold change after
the fact — you can see which edges would survive a higher bar without
recomputing anything.

**Why link on update as well as create?** A memory whose content changed has a
different neighbourhood. Skipping updates would leave edges pointing at what a
memory used to be about.
