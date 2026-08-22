# Temporal model — bitemporal facts

EngramDB tracks **two independent time dimensions** for every memory. That's
what makes it possible to answer *"what did the agent believe about this, at
time T?"* — in plain SQL, with no graph database.

| Dimension | Columns | Question it answers |
|---|---|---|
| **World time** (validity) | `valid_from`, `valid_to` on `memories` (and on each `memory_versions` row) | *When was this fact true in the world?* |
| **System time** (knowledge) | `created_at`, `updated_at`, plus the `memory_versions` chain and `superseded_at` | *When did we come to believe it?* |

The two are genuinely independent: an agent can learn **today** (system time)
that the user moved **last March** (world time) by passing a backdated
`valid_from`.

## The shape of the data

The canonical `memories` row always holds the **current** generation of a fact
and **keeps a stable `id`** for the life of that `(user_id, memory_key)`. Prior
generations live in `memory_versions` with **closed** validity windows that tile
the past without gaps or overlaps:

```
memory_key = "fact:city"        (one canonical row, stable id)

memory_versions  v1  [2026-01-01 ── 2026-03-01)   "Lives in Mumbai."   status=superseded
memory_versions  v2  [2026-03-01 ── 2026-06-01)   "Lives in Pune."     status=superseded
memories (current)   [2026-06-01 ──        ∞ )    "Lives in Berlin."   valid_to IS NULL
```

Window *N* closes at exactly the instant window *N+1* opens, so for any instant
there is exactly one generation in effect.

**Why the id is stable.** Five tables reference `memories.id` — `memory_acls`,
`memory_links`, `memory_versions`, `retrieval_log_items`, `observations` — and
clients hold ids for `/share`, `/acl`, `/status`, `/versions`, `/links`. If a
supersession inserted a *new* row, the new current fact would silently inherit
none of them: a team-shared memory would become private on its next update, and
graph links would point at history. Keeping the canonical id and versioning
underneath avoids that entire class of bug.

## Writing: supersession

On `POST /memories/upsert` for an existing key with different content:

1. The prior generation is snapshotted into `memory_versions` with
   `valid_to = <new valid_from>` and `status = "superseded"`.
2. The canonical row is updated in place: new content, `valid_from = <new
   valid_from>`, `valid_to = NULL`, `version += 1`.
3. A `memory.superseded` lifecycle event fires (webhook + WebSocket) alongside
   `memory.updated`.

Two optional fields on the upsert payload:

- **`valid_from`** — when the fact became true. Defaults to `now()`; pass an
  earlier timestamp to backdate.
- **`invalidate_only`** — close the current window with **no replacement** (the
  fact simply stopped being true). The row is marked `stale`, remains queryable
  as-of, and drops out of current-fact retrieval. Also available as
  `POST /memories/{id}/invalidate`.

`superseded_by` on `memories` is reserved for the rarer case where a
*different* canonical row replaces this one (a key rename or explicit
replacement) — in-place supersession is recorded by the version chain.

## Reading: as-of queries

`as_of` is accepted by `POST /memories/search`, `GET /memories`, and
`POST /memories/assemble-context`.

Resolution has two steps, and the split matters:

1. **Candidate selection (SQL).** A row qualifies if *either* its own window
   contains `as_of` **or** one of its historical generations does (an `EXISTS`
   over `memory_versions`). Filtering only on the canonical window would
   wrongly drop every fact that has been superseded since `as_of` — which is
   precisely what an as-of query is asking for.
2. **Projection.** Each result is projected to the generation valid at `as_of`:
   content, scores, authority, and window are overlaid from the matching
   version. A memory with no generation valid then is dropped entirely.

Ranking uses the *current* row's embedding — the fact **slot** ("the user's
city") embeds similarly regardless of which value it currently holds — and
projection then resolves *which value* that slot held. Note the consequence:
semantic search over historical content itself is not supported, because
embeddings live on `memories`, not `memory_versions`.

`GET /memories/{id}/timeline` returns the whole chain, oldest first, each
generation with its window, when the system recorded it, and a diff against the
previous generation.

## Default behaviour and the feature flag

`ENABLE_TEMPORAL_VALIDITY` (default `false`) governs only the **default** for
queries that pass no `as_of`:

| Flag | No `as_of` given | With `as_of` |
|---|---|---|
| `false` (default) | `valid_to IS NULL OR valid_to > now()` — identical to pre-migration behaviour, so an open future window still counts as current | Point-in-time resolution |
| `true` | `valid_to IS NULL` — current facts only; a closed window is history, full stop | Point-in-time resolution |

`as_of` works regardless of the flag. A fresh `docker compose up` behaves
exactly as it did before this feature until you set the flag.

## Indexes

- `ix_memories_current` — partial, `(user_id, memory_key) WHERE valid_to IS NULL`.
  The hot path for upsert targeting and current-fact reads.
- `ix_memories_user_validity` — `(user_id, valid_from, valid_to)` for as-of range scans.
