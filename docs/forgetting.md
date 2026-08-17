# Forgetting

Most memory systems only add. That is the wrong shape for a long-lived agent: a
store that never forgets slowly fills with stale, low-value, and occasionally
harmful facts, and every retrieval pays for them. EngramDB treats forgetting as a
first-class, *auditable* operation — nothing leaves active recall silently.

There are three mechanisms, deliberately separate because they answer three
different questions.

| Mechanism | Question it answers | Reversible? | Audited |
|-----------|--------------------|-------------|---------|
| **Importance decay** | "Is this still worth ranking highly?" | Yes — reconsolidation restores it | Counter only |
| **Retention archival** | "Should this still be in active recall?" | Yes — flip status back to `active` | `forgetting_log` |
| **Erasure** | "Must this cease to exist?" | **No** | `forgetting_log` + content hash |

All three are **off or non-destructive by default**. A fresh `docker compose up`
behaves exactly as it did before this feature existed.

---

## 1. Importance decay (Ebbinghaus)

Importance decays exponentially since a memory was last *used*:

```
importance ← max(importance × 2^(−Δt / DECAY_HALF_LIFE_HOURS), DECAY_FLOOR)
```

- `Δt` is measured from **last activity** — `max(updated_at, last access)` — not
  from creation. A fact recalled yesterday is fresh even if it was written a year
  ago.
- It is a true half-life: after `DECAY_HALF_LIFE_HOURS` of disuse, importance has
  halved. (The naive `exp(−Δt / half_life)` leaves 37%, not 50% — an easy bug to
  ship and a hard one to notice.)
- `DECAY_FLOOR` (default `0.05`) means decay never erases a memory. It sinks in
  the ranking; it does not disappear.
- **Pinned memories are skipped entirely** (see below).

Run by the `decay_importance` scheduler job (every 6h by default), or on demand:

```bash
curl -X POST 'localhost:8100/api/v1/forgetting/decay?dry_run=true'
```

`dry_run=true` is the default on that endpoint — it reports what *would* decay
without writing.

### Reconsolidation on retrieval

Decay alone is a ratchet: everything eventually flattens to the floor. The
counterweight is reconsolidation — the memory-science observation that recalling
a memory strengthens it. When `ENABLE_RECONSOLIDATION=true`, every memory
returned by a search gets

```
importance ← min(importance + RECONSOLIDATION_BOOST, 1.0)
```

and its recency score refreshed. The net effect: **use**, not age, decides what
stays important.

Two deliberate exclusions:

- **`as_of` queries never reconsolidate.** Auditing what the agent believed last
  March must not change what it believes now. Reading history does not rewrite it.
- The boost is applied *after* the response is assembled, so the scores you get
  back are the ones that produced that ranking.

---

## 2. Retention archival

Decay changes ranking; archival removes a memory from active recall. The decision
is a blended retention score rather than a bare importance threshold:

```
retention = 0.4 × recency + 0.4 × importance + 0.2 × normalised_access_count
```

A rarely-flagged-important but frequently-recalled fact survives; a stale, unused,
low-value one is archived. Guards:

- Memories younger than `FORGETTING_MIN_AGE_DAYS` (default 14) are never archived.
- Distilled layers (`persona`, `scenario` — see `FORGETTING_EXEMPT_LAYERS`) are
  exempt; they are deliberate artefacts, not raw churn.
- Pinned memories are exempt.
- Every archival writes a `forgetting_log` row with `action="decayed_archive"`.

Archival sets `status="archived"`. The row is intact — flip the status back to
recover it.

---

## 3. Pinning

`pinned=true` exempts a memory from decay *and* archival, permanently. It is the
escape hatch for facts that must survive however rarely they are used — an
allergy, a legal constraint, a hard user preference.

```bash
# On write
curl -X POST localhost:8100/api/v1/memories/upsert \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"…","memory_key":"health:allergy","memory_type":"semantic",
       "content":"Severe peanut allergy.","pinned":true}'

# Or afterwards
curl -X PATCH localhost:8100/api/v1/memories/{id}/pin \
  -H 'Content-Type: application/json' -d '{"pinned":true}'
```

Omitting `pinned` on a later upsert **leaves the pin alone**. Pinning is an
operator decision, so a routine content update must not silently clear it. Pass
`pinned: false` explicitly to unpin.

---

## 4. Auditable erasure (GDPR right-to-be-forgotten)

Erasure is a hard `DELETE`: the memory, its versions, and (via FK cascade) its
links, ACL grants, access logs, and retrieval-log items are gone. What remains is
a tombstone in `forgetting_log`:

| Column | Purpose |
|--------|---------|
| `memory_id`, `user_id` | What was erased, for whom — **no FK**, so the row outlives the deleted memory |
| `action` | `user_erasure` / `admin_erasure` |
| `reason`, `triggered_by` | Why, and what path requested it |
| `content_hash` | **SHA-256 of the erased content** |
| `occurred_at` | When |

The content hash is the point of the design. An auditor can be handed the
original text and shown that *this* is what was deleted — without EngramDB having
retained a copy. That is the difference between deletion you can prove and
deletion you merely assert.

### Endpoints

```bash
# One memory — irreversible, requires the `erase` scope
curl -X DELETE 'localhost:8100/api/v1/memories/{id}?mode=erase&reason=gdpr+request' \
  -H 'X-API-Key: …'

# Everything for a user — full right-to-be-forgotten
curl -X DELETE 'localhost:8100/api/v1/users/{user_id}/memories?mode=erase' \
  -H 'X-API-Key: …'
```

`DELETE /memories/{id}` **without** `mode=erase` archives instead — the default is
non-destructive, so an accidental delete costs nothing.

### The `erase` scope

Erasure requires an API key whose `scopes` names `erase` (or `*`). Unlike every
other scope check, a key with *blank* scopes is **not** treated as unrestricted
here: irreversible deletion must be granted deliberately, never inherited from an
empty field.

### Over MCP

The `forget_memory` MCP tool is gated twice: `MCP_ENABLE_FORGET` must be `true`
(default `false`, and while off the tool is not even listed to agents), and the
calling key still needs the `erase` scope. An agent should not be one
hallucinated tool call away from destroying data.

---

## 5. Expiry

Memories with `expires_at` in the past are retracted by the `cleanup_expired` job.
The outcome is unchanged from earlier versions — `status="retracted"` — but each
retraction now writes a `forgetting_log` row with `action="expired"`, so
"why did this memory stop being retrievable?" is always answerable.

---

## Reading the audit trail

```bash
curl 'localhost:8100/api/v1/forgetting/log?user_id={user_id}&limit=50'
```

Newest first. This is the answer to "where did that memory go?" — every decay
archival, expiry, and erasure, with who triggered it and why.

Prometheus exposes the same activity as counters:

```
engramdb_memory_forgetting_total{action="decayed"}
engramdb_memory_forgetting_total{action="decayed_archive"}
engramdb_memory_forgetting_total{action="expired"}
engramdb_memory_forgetting_total{action="user_erasure"}
```

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_DECAY` | `false` | Master switch for importance decay |
| `DECAY_HALF_LIFE_HOURS` | `720` | Half-life in hours (30 days) |
| `DECAY_FLOOR` | `0.05` | Importance never decays below this |
| `SCHEDULER_ENABLE_DECAY` | `true` | Register the decay job (still needs `ENABLE_DECAY`) |
| `SCHEDULER_DECAY_INTERVAL` | `21600` | Seconds between decay runs (6h) |
| `ENABLE_RECONSOLIDATION` | `false` | Boost importance when a memory is recalled |
| `RECONSOLIDATION_BOOST` | `0.02` | Per-recall importance increase (capped at 1.0) |
| `MCP_ENABLE_FORGET` | `false` | Expose the `forget_memory` MCP tool |
| `FORGETTING_RETENTION_THRESHOLD` | `0.35` | Archive below this retention score |
| `FORGETTING_MIN_AGE_DAYS` | `14` | Never archive memories younger than this |
| `FORGETTING_EXEMPT_LAYERS` | `persona,scenario` | Layers never archived |

Note the double gate on decay: `SCHEDULER_ENABLE_DECAY` registers the job, but the
job is only *enabled* when `ENABLE_DECAY` is also true, and it no-ops if the flag
is turned off between registration and execution. A default deployment decays
nothing.

---

## SDK

```python
await client.pin_memory(memory_id, pinned=True)
await client.erase(memory_id, reason="user requested deletion")   # needs `erase` scope
await client.erase_user(user_id)
log = await client.forgetting_log(user_id=user_id)
```

```ts
await db.memories.pin(memoryId, true);
await db.memories.erase(memoryId, 'user requested deletion');
await db.forgetting.eraseUser(userId);
const log = await db.forgetting.log({ userId });
```

---

## Design notes

**Why decay and archival are separate.** Decay is continuous and reversible;
archival is a discrete, audited state change. Collapsing them would mean either
auditing every score tweak (noise) or making archival un-auditable (worse).

**Why the audit row has no foreign key.** A tombstone that cascades away with the
memory it describes is not a tombstone. `forgetting_log.memory_id` is a plain
UUID column precisely so the row survives the hard delete.

**Why erasure keeps a hash and not the content.** Keeping the content would
defeat the erasure; keeping nothing would make it unprovable. A SHA-256 is the
only artefact that satisfies both constraints.

**Why the default `DELETE` archives.** Destructive-by-default HTTP verbs are how
data gets lost. `mode=erase` makes the irreversible path explicit at the call
site, and the `erase` scope makes it explicit at the credential level.

See also: [`docs/temporal-model.md`](temporal-model.md) — invalidating a fact
(closing its validity window) is *not* forgetting. An invalidated fact remains
fully queryable via `as_of` and `/timeline`; it simply stopped being true.
