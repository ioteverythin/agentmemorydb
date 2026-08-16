# TencentDB Agent Memory — Flaw Analysis & How EngramDB Improves On It

This document catalogues the concrete flaws we found in
[TencentCloud/TencentDB-Agent-Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory)
after a deep read of all four of its services (MemoryCore, MemoryProxy,
MemoryKnowledge, MemoryPanel) and its SDKs, and records the good ideas we
deliberately adopted — implemented so as to avoid the flaws that accompanied
them in the original.

The analysis is code-level and cites specific files/lines in the upstream repo
(commit fetched 2026-08-09). Severities are our assessment.

---

## 1. What Tencent Agent Memory is

A four-service TypeScript stack (plus TS/Python SDKs) that gives coding agents
persistent memory:

- **MemoryCore** — the memory kernel. Implements a four-layer "memory pyramid"
  (`L0` raw conversation → `L1` atomic facts → `L2` scenario blocks → `L3`
  persona), dual storage (standalone `node:sqlite` + `sqlite-vec` + FTS5, or
  Tencent Cloud VectorDB + COS + Redis), hybrid retrieval (BM25 + vector +
  client-side RRF), LLM-based extraction/dedup, and age-based forgetting.
- **MemoryProxy** — an LLM API proxy that intercepts Claude Code / CodeBuddy
  traffic to auto-extract memories, inject context, and handle `mem:` commands.
- **MemoryKnowledge** — a RAG service: LLM-Wiki (docs → structured wiki pages)
  and Code-Graph (repo → symbol/call graph).
- **MemoryPanel** — a control plane (teams, agents, ACLs, asset loadouts).

The headline ideas are strong. The execution has serious security, correctness,
and operability gaps.

---

## 2. Notable good ideas worth adopting

1. **The L0→L3 memory pyramid.** Distilling raw conversation into progressively
   more stable layers, and treating higher layers as cacheable "bootstrap"
   context while lower layers serve query-specific recall, is a genuinely good
   model.
2. **Hybrid retrieval with Reciprocal Rank Fusion.** Fusing dense (vector) and
   sparse (BM25/FTS) rankings via RRF (k=60) surfaces both semantic and
   lexically-exact matches without cross-calibrating raw scores.
3. **Prompt-cache-aware injection.** Appending stable content (persona, scene
   navigation) to the system prompt while keeping volatile hits in the user
   prompt preserves the provider's prompt-prefix cache across turns.
4. **Budgeted recall.** Capping recall by item count, character budget, and
   timeout so memory never overwhelms the context window.
5. **Capability-flag store abstraction** with documented graceful degradation
   (callers pick strategies by `vectorSearch`/`ftsSearch`/`nativeHybridSearch`).

We adopted #1–#4 directly (see §4). We already had a capability-degrading
repository layer (#5).

---

## 3. Flaws (with upstream file:line evidence)

### 3.1 Security — MemoryCore

| # | Sev | Flaw | Evidence |
|---|-----|------|----------|
| C1 | **High** | v2/v3 data-plane Bearer token is captured but **never validated** — auth is off by default, so every memory read/write/delete endpoint is open in the default config. | `MemoryCore/src/gateway/v2-router.ts:344-362`; `server.ts:1084-1086` |
| C2 | **High** | Tenant identity is entirely client-asserted via the spoofable `x-tdai-service-id` header and body fields, with no binding to an authenticated principal. Even with the one shared secret set, any client can read/write any tenant by changing headers. | `v2-router.ts:351,376`; `v2-schemas.ts:326-355` |
| C3 | **High** | Destructive `POST /v2/instance/destroy` sits behind the same default-open gate — anyone reaching the port can wipe any instance. | `server.ts:819-833` |
| C4 | **High** | Auto-recall performs **no tenant filtering** — `searchL1Fts/Vector/Hybrid` are all called without an `IsolationFilter`, so a shared instance injects other tenants' memories into the prompt. | `auto-recall.ts:505,538,596,660,702` |
| C5 | **High** | Isolation "enforcement" is dead code: `assertIsolation` never throws and silently fills missing ids with `"default"`, co-mingling writes across callers. | `core/store/isolation.ts:73-101` |
| C6 | **High** | User API keys stored **in plaintext** with direct-equality lookup (no hashing, no constant-time compare). DB theft = all credentials. | `metadata/store/sqlite-adapter.ts:143,499-501` |
| C7 | **High** | Stored-memory **prompt injection**: recalled content is spliced into prompts inside forgeable pseudo-tags, and L2 extraction runs a **tool-armed LLM** over that same user-controlled content. | `auto-recall.ts:270-280`; `core/scene/scene-extractor.ts` |

### 3.2 Security — MemoryProxy & SDK

| # | Sev | Flaw | Evidence |
|---|-----|------|----------|
| P1 | **High** | v2 SDK **disables TLS verification by default**; the ESM `require("undici")` fallback throws and then sets `NODE_TLS_REJECT_UNAUTHORIZED=0`, disabling TLS **process-wide**. | `sdk/.../typescript/src/http.ts:23-24,48-62`; Python `_http.py:62,122` |
| P2 | **High** | Identity spoofing when auth disabled — `userId` derived from client headers becomes the memory namespace + billing key + isolation key. | `auth.ts:71`; `anthropicHandler.ts:652-656` |
| P3 | **High** | Memory-bridge L1 fast-path injects a session's `team/user/agent` into the memory query **without verifying the caller owns that conversation**. | `memory/memory-bridge.ts:72-84,105-113` |
| P4 | **High** | Cross-tenant prompt injection: up to 2 **other agents'** chat memories imported into context, gated only by a team-id string match. | `injection/injectors/tdai-fixed-asset.ts:79-114` |
| P5 | Med | Raw API keys + 5000-char prompt previews retained in an in-memory ring buffer and logged to stderr. | `identity.ts:86-95,366-403` |
| P6 | Med | Full conversation content fanned out to Opik/Langfuse/ClickHouse; `langfuse.debug=true` ships the raw body + headers. | `opik.ts:115,221`; `common/langfuse-debug.ts:90-195` |

### 3.3 Security & ops — Deploy / Knowledge / Panel

| # | Sev | Flaw | Evidence |
|---|-----|------|----------|
| D1 | **High** | Gateway auth is disabled by default and **effectively cannot be enabled** (a documented unfixed proxy bug forces the key empty). | `deploy/global-images/.env.example:80`; `start-memory-core.sh:22-25` |
| D2 | **High** | Hardcoded default inter-service credential `"local"`. | `start-memory-hub.sh:26`, `start-proxy.sh:25` |
| D3 | **High** | Agent-facing KS `tools/*` endpoints have no per-caller authorization and are mandated to be exposed over **plain HTTP externally**; a guessable `knowledge_id` is the only secret. | `MemoryKnowledge/src/routes/tools.ts:194-292` |
| D4 | **High** | **No TLS anywhere** — every service binds `0.0.0.0` over `http://`; user keys, LLM keys, and cloned source cross the network in cleartext. | `start-memory-core.sh:132`, `start-proxy.sh:80` |
| D5 | Med | Blacklist-only SSRF check for git clone, bypassable via DNS rebinding and disableable with an env var. | `git-fetcher.ts:25-37,69` |
| D6 | Med | Long-lived bearer key persisted in browser `localStorage`; any XSS exfiltrates a permanent credential. | `web/src/lib/panelSession.ts:43-49` |
| D7 | Med | **CI tests essentially nothing** — no `test`/`typecheck`/`build`/`lint`; three of four services never touched. **Zero test files** exist in the entire repo. | `.github/workflows/pr-ci.yml` |

### 3.4 Correctness & scalability

| # | Sev | Flaw | Evidence |
|---|-----|------|----------|
| X1 | Med | Lost updates — no compare-and-swap anywhere; concurrent `version+1` writes silently clobber each other. | `v2-router.ts:1005-1049` |
| X2 | Med | Dedup **fails open** (LLM failure ⇒ store everything) and is session-scoped, so cross-session duplicates are structurally undetectable. | `l1-dedup.ts:186-195`; `l1-extractor.ts:271` |
| X3 | Med | Forgetting is naive age-based deletion, **off by default**, with no importance/access signal — a priority-90 persona fact dies the same day as chit-chat. | `memory-cleaner.ts:130-161` |
| X4 | Med | Ingestion embeds **sequentially, one HTTP call per message**; retries disabled; failed rows written vector-less with no backfill. | `v2-router.ts:717-722`; `embedding.ts:370` |
| X5 | Med | Synchronous SQLite (`DatabaseSync`) on the HTTP event loop — every KNN scan blocks all concurrent requests. | `core/store/sqlite.ts:17,27` |
| X6 | Med | SQLite isolation is post-filter with fixed over-fetch (`limit*5` global) → tenant recall starvation as tenant count grows. | `sqlite.ts:2983-3006,1398-1453` |
| X7 | Low-Med | 48-bit message IDs (`msg-` + 12 hex) → birthday collisions ~16M msgs; `ON CONFLICT` then overwrites a **different tenant's** message. | `v2-router.ts:702`; `sqlite.ts:800-813` |
| X8 | Low-Med | Audit trail cannot roll back — stores only who/when/which, no prior content; version numbers exist but versions are unrecoverable. | `core/store/types.ts:475-507` |

### 3.5 Vendor lock-in & bus factor

- Service mode hard-requires Tencent VectorDB + COS + Redis; COS URL parsing
  accepts only `*.myqcloud.com`/`*.tencentcos.cn`; no S3/GCS/pgvector/Qdrant
  adapters despite the "backend-agnostic" interface (`credential-provider.ts:226-242`).
- The entire Code-Graph feature rests on one individual's native package
  `@colbymchenry/codegraph` with per-platform binaries — supply-chain risk with
  no vendoring/fallback.

---

## 4. How EngramDB is better

EngramDB was already SQL-native (PostgreSQL + pgvector), versioned,
auditable, and API-key authenticated. In response to this analysis we adopted
Tencent's best ideas **without** their flaws, and fixed a set of our own latent
bugs. Every item below ships with tests (357 passing: 346 unit + 11 integration
against real PostgreSQL + pgvector).

### 4.1 Adopted Tencent's good ideas — safely

| Tencent idea | Our implementation | How we avoid their flaw |
|---|---|---|
| L0→L3 memory pyramid | `MemoryLayer` enum (`raw`/`atom`/`scenario`/`persona`) + a `layer` column on `memories`, filterable in search (`app/models/enums.py`, `migration 005`). | Layers are first-class SQL, not markdown files on disk; retrieval can filter by layer. |
| Hybrid retrieval + RRF | `app/utils/rrf.py` (pure, unit-tested) fuses dense vector + sparse PostgreSQL full-text (`ts_rank` + `websearch_to_tsquery`) rankings; strategy reported as `hybrid_rrf`. | Server-side FTS via the existing `search_vector` tsvector trigger (no client RRF over a starved candidate set, cf. **X6**); `websearch_to_tsquery` removes the FTS-injection foot-gun. |
| Prompt-cache-aware, budgeted injection | New `ContextAssemblyService` + `POST /api/v1/memories/assemble-context`: orders stable layers (persona/scenario) first, caps by item count + char budget, reports token estimate + truncation. | — |
| Injecting memory into prompts | Every memory is escaped (`app/utils/injection_safety.py`) against delimiter forgery and instruction lead-ins, then wrapped in an explicitly-untrusted `<untrusted-memory>` fence with a preamble telling the model to treat it as data. | Directly counters Tencent's stored-prompt-injection (**C7**, **P4**); tested that a memory containing `</untrusted-memory>` cannot break the fence. |
| Query-time recall tuning | `hnsw.ef_search` is now actually applied per query (was decorative). | — |

### 4.2 Tenant isolation (counters C1, C2, C4, C5, P2, P3)

- New `enforce_tenant()` boundary (`app/core/auth.py`) wired into the memory
  endpoints: an authenticated key for user A **cannot** read or mutate user B's
  memories by passing a different `user_id`. Service/admin keys with the `*`
  scope may act cross-tenant. Safe no-op when auth is disabled. Unit-tested.
- CORS no longer emits the invalid/unsafe `allow_origins:["*"] +
  allow_credentials:true` combination; credentials are only enabled for explicit
  origins (`app/main.py`, configurable via `cors_allow_origins`).

### 4.3 Correctness fixes to our own codebase

These are latent bugs the analysis surfaced in EngramDB itself:

1. **Scheduler now actually runs.** `main.py` launched `start()`/`stop()`
   without `await` on an infinite-loop coroutine (zero jobs ran) and built a
   second scheduler instance than the one `/scheduler` reported. Now launched as
   a cancellable `asyncio.create_task` on the `get_scheduler()` singleton.
2. **Scheduler intervals were off by 60×** — settings named in seconds were
   consumed as minutes. `ScheduledJob` now takes `interval_seconds`.
3. **`_prune_access_logs` referenced a non-existent column** (`accessed_at` →
   `created_at`); it would raise `UndefinedColumn` on every run.
4. **MCP `record_event` was broken three ways** (wrong method name, wrong field,
   NULL run_id into a NOT NULL column). Fixed to call `create_event(payload=…)`
   and require `run_id`.
5. **MCP `consolidate_memories` ignored `dry_run`** — a "preview" destructively
   merged and committed. Dry-run now reports duplicate groups with no mutation.
6. **Self-referential contradiction link.** Upsert created a `supersedes` link
   from a memory to itself. Removed; the `MemoryVersion` snapshot (now with the
   full governance/validity envelope) is the authoritative supersession record.
7. **Lossy version snapshots** (**counters X8**): `MemoryVersion` now captures
   `memory_type`, `scope`, `layer`, `authority_level`, and the validity window,
   so a prior version can be restored faithfully.
8. **Upsert project-scope leak.** `find_active_by_key` omitted the `project_id`
   predicate when it was `None`, letting a user-scoped lookup match a
   project-scoped row. Now binds `project_id IS NULL` explicitly.
9. **Vocabulary drift** between the MCP tools and the server enums
   (`SourceType`/`EventType`) is aligned, so MCP-written events/memories are no
   longer orphaned from the pipeline.
10. **Dead per-query work** (an unused vector-string build) removed from the hot
    path; retrieval over-fetch is configurable.
11. **`SET LOCAL hnsw.ef_search` bind-parameter bug** — caught by the new
    integration test; PostgreSQL rejects `SET … = $1`, which would have broken
    *every* production vector search. Now inlined as a coerced int.

### 4.4 What we deliberately did **not** copy

- No plaintext credential storage (we hash API keys), no TLS-disabling SDK
  defaults, no client-asserted tenancy, no conversation content fanned out to
  third-party telemetry, no hard dependency on a single cloud vendor or a
  single-maintainer native binary.

---

## 5. Test evidence

```
346 unit tests + 11 integration tests (PostgreSQL 16 + pgvector) = 357 passing
```

New coverage added by this work: RRF fusion (`test_rrf.py`), injection
sanitisation (`test_injection_safety.py`), memory-pyramid layers + lossless
snapshots + context-assembly budgets and injection safety
(`test_memory_pyramid.py`), tenant isolation (`test_tenant_isolation.py`), MCP
correctness fixes (`test_mcp_fixes.py`), and an end-to-end hybrid RRF / FTS /
layer-filter / context-assembly integration suite against real Postgres +
pgvector (`test_hybrid_rrf_search.py`).
