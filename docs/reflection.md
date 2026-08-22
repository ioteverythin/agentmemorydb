# Sleep-Time Consolidation (Reflection)

Every other write path in EngramDB records something that *happened*: a user said
it, a tool returned it, an agent concluded it in the moment. Reflection is the
one pass that **derives**. It looks at a group of related memories together and
writes down what follows from the group but appears in none of its members.

```
"Uses Postgres for the analytics service."
"Complained that the ORM's migrations are slow."     ──▶  "The user is standardising
"Asked twice about connection pooling."                    on Postgres and is hitting
                                                           operational pain with it."
```

No single memory says that. The cluster does.

The name is borrowed from the sleep-consolidation literature, and so is the
scheduling: a slow cycle (daily by default), off the request path, when nothing
is waiting on it. Reflection is the most expensive thing EngramDB does — it is
the only feature that calls an LLM per cluster — so it never runs inline with a
write or a search.

---

## The pipeline

```
recent atoms ──cluster──▶ groups ──LLM──▶ insight ──▶ scenario memory
     │                       │                            │
  last 7 days           ≥3 members                   derived_from links
  status=active         cosine ≥ 0.75                back to every source
  layer=atom            top 10 by size               origin=system
```

**Candidates.** Active `atom`-layer memories updated within
`REFLECTION_LOOKBACK_HOURS`, newest first, capped at
`REFLECTION_MAX_MEMORIES`. Only atoms: `raw` is unprocessed noise, and
`scenario`/`persona` are already distilled — reflecting over them would compound
abstraction rather than add insight.

**Clustering.** Greedy agglomeration by cosine similarity over the embeddings
already stored on each memory, falling back to word-overlap when a memory has no
embedding. A memory joins a cluster if it is similar enough to that cluster's
*seed*, not its centroid: with clusters this small the centroid drifts toward
whatever joined first, quietly widening the cluster until unrelated memories get
swept in. Clusters below `REFLECTION_MIN_CLUSTER_SIZE` (default 3) are dropped —
a pair is a coincidence, not a pattern — and the largest clusters get the LLM
budget first.

The clustering is deliberately simple. Reflection quality lives in the prompt,
not the algorithm; a fancier clusterer would add failure modes without adding
insight.

**Insight.** One LLM call per cluster. The model is asked for a single sentence
stating what follows from the group, and is told to answer `NONE` when the
cluster supports nothing worth saying — a reflection system that always finds
something is one that invents things. The memory text is passed as data with an
explicit instruction never to follow directives inside it.

**Write.** The insight becomes an ordinary memory: `layer="scenario"`,
`origin="system"`, `authority_level=1`, `confidence=0.6`. It is retrievable like
anything else and it can never outrank a memory of something actually said. Each
insight is linked `derived_from` every memory in its cluster, so "why does the
agent believe this?" is one graph hop away.

---

## Three properties that make it safe to leave on

### 1. It fails closed, and loudly

Reflection is the one feature where a misconfigured deployment looks exactly like
a working one: both produce no insights. So a pass with no LLM provider is
recorded as `status="skipped"`, `skipped_reason="no_llm_provider"` — never as a
success that happened to find nothing.

Every pass writes a `consolidation_runs` row, whatever the outcome:

| `skipped_reason` | Meaning |
|------------------|---------|
| `disabled` | `ENABLE_REFLECTION` is off |
| `no_llm_provider` | **Feature on, no model configured.** The one to alert on |
| `too_few_memories` | Fewer candidates than the minimum cluster size |
| `no_clusters` | Candidates exist but none are similar enough to group |
| `dry_run` | Clustered and reported, deliberately did not call the model |

A provider error mid-pass does not lose the run either: the cluster's error is
recorded in `details` and the pass continues with the next cluster.

### 2. Everything it writes is traceable

`origin="system"` puts insights at EngramDB's own trust level (see
[`docs/provenance.md`](provenance.md)), and the `derived_from` links name the
exact evidence. An insight that turns out to be wrong can be traced to the
memories that produced it — and those can be corrected or erased.

### 3. It is idempotent per cluster

The insight's `memory_key` is a hash of its cluster's member keys. Re-reflecting
over the same group updates that insight through the ordinary supersession path
(with a version bump and a timeline entry) instead of accumulating near-duplicate
"insights" that all say roughly the same thing.

---

## Running it

```bash
# Cluster and report without calling the model — free, and shows what it would group
curl -X POST 'localhost:8100/api/v1/consolidation/reflect?user_id={id}&dry_run=true'

# Run for real
curl -X POST 'localhost:8100/api/v1/consolidation/reflect?user_id={id}'

# Or trigger the scheduled job across all users
curl -X POST localhost:8100/api/v1/scheduler/run/reflect_and_promote

# Pass history — newest first
curl 'localhost:8100/api/v1/consolidation/runs?user_id={id}'
```

A run response:

```json
{
  "status": "completed",
  "memories_considered": 42,
  "clusters_found": 3,
  "insights_created": 2,
  "duration_ms": 1840,
  "details": {"clusters": [
    {"size": 5, "memory_key": "reflection:a1b2…", "sources": ["…", "…"]},
    {"size": 3, "insight": null}
  ]}
}
```

The second cluster produced nothing — the model answered `NONE`. That is a normal
outcome and it is recorded rather than hidden.

---

## Observability

```
engramdb_reflections_total{status="completed"}
engramdb_reflections_total{status="skipped"}
engramdb_reflection_insights_total
```

A steady stream of `skipped` with no `completed` is a reflection system that
isn't reflecting. That is precisely the signal the status label exists to give
you; check `consolidation_runs.skipped_reason` for which kind of nothing it is.

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_REFLECTION` | `false` | Master switch |
| `LLM_PROVIDER` | `none` | Required — without it every pass skips |
| `REFLECTION_LOOKBACK_HOURS` | `168` | How far back to draw candidates (7 days) |
| `REFLECTION_MAX_MEMORIES` | `200` | Candidates considered per pass |
| `REFLECTION_MIN_CLUSTER_SIZE` | `3` | Below this a group is a coincidence |
| `REFLECTION_SIMILARITY_THRESHOLD` | `0.75` | Cosine similarity to join a cluster |
| `REFLECTION_MAX_CLUSTERS` | `10` | Caps LLM calls per pass |
| `SCHEDULER_REFLECTION_INTERVAL` | `86400` | Seconds between passes (daily) |
| `SCHEDULER_ENABLE_REFLECTION` | `true` | Register the job (still needs `ENABLE_REFLECTION`) |

The job is double-gated: `SCHEDULER_ENABLE_REFLECTION` registers it, but it is
only *enabled* when `ENABLE_REFLECTION` is also true, and the handler re-checks
the flag at execution time. A default deployment never calls an LLM.

---

## Design notes

**Why not fold this into distillation?** Distillation is deterministic and
structural: it rolls atoms into scenario blocks and a persona summary by topic,
with no model required. Reflection is generative and optional. Merging them
would mean either making distillation depend on an LLM key — breaking the
zero-config path — or making reflection run on distillation's schedule, which is
far too often for something that costs a model call per cluster.

**Why `NONE` rather than "return your best guess"?** A model asked for an insight
will always produce one. The explicit escape hatch is what keeps the store from
filling with confident restatements of what it already knows.

**Why link back to sources instead of embedding them in the payload?** Both,
actually — the payload records the source *keys* for a human reading the row, and
the `derived_from` links are the queryable version that survives the sources being
renamed or superseded.

**Why `confidence=0.6`?** High enough to be retrieved, low enough that a directly
stated fact wins a ranking against it. A derived belief should lose to an
observed one.

See also: [`docs/provenance.md`](provenance.md) for what `origin="system"` means
for ranking, and [`docs/forgetting.md`](forgetting.md) — insights decay and
archive like any other memory, so a reflection nobody ever retrieves eventually
falls out of active recall on its own.
