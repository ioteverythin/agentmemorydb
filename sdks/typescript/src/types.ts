/** Type definitions for the EngramDB TypeScript SDK. */

// ── Configuration ───────────────────────────────────────────────

export interface EngramDBConfig {
  /** Base URL of the EngramDB server */
  baseUrl: string;
  /** API key for authentication */
  apiKey?: string;
  /** Request timeout in milliseconds (default: 30000) */
  timeout?: number;
  /** Custom headers to include in all requests */
  headers?: Record<string, string>;
}

// ── Memory Types ────────────────────────────────────────────────

export type MemoryType = 'working' | 'episodic' | 'semantic' | 'procedural';
export type MemoryScope = 'user' | 'project' | 'team' | 'global';
export type MemoryStatus = 'active' | 'superseded' | 'stale' | 'archived' | 'retracted';
export type LinkType = 'derived_from' | 'contradicts' | 'supports' | 'related_to' | 'supersedes';
export type SourceType = 'human_input' | 'agent_inference' | 'system_inference' | 'external_api' | 'reflection' | 'consolidated';

export interface Memory {
  id: string;
  user_id: string;
  project_id: string | null;
  memory_key: string;
  memory_type: MemoryType;
  scope: MemoryScope;
  content: string;
  content_hash: string;
  payload: Record<string, unknown> | null;
  source_type: SourceType;
  /** Trust domain the write came from — caps authority, gates quarantine. */
  origin: MemoryOrigin;
  /** Pointer to the specific writer: a URL, tool name, or document id. */
  origin_ref: string | null;
  source_event_id: string | null;
  source_observation_id: string | null;
  source_run_id: string | null;
  status: MemoryStatus;
  /** Pinned memories are exempt from importance decay and retention archival. */
  pinned: boolean;
  authority_level: number;
  confidence: number;
  importance_score: number;
  recency_score: number;
  valid_from: string | null;
  valid_to: string | null;
  expires_at: string | null;
  last_verified_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface MemoryUpsertInput {
  userId: string;
  memoryKey: string;
  content: string;
  memoryType?: MemoryType;
  scope?: MemoryScope;
  projectId?: string;
  embedding?: number[];
  payload?: Record<string, unknown>;
  sourceType?: SourceType;
  confidence?: number;
  importanceScore?: number;
  authorityLevel?: number;
  validFrom?: string;
  validTo?: string;
  expiresAt?: string;
  isContradiction?: boolean;
  /** Pin this memory so it is never decayed or auto-archived. */
  pinned?: boolean;
  /** Trust domain of the writer. Attribute honestly: it caps the authority
   *  this write may claim and decides whether it is quarantined. */
  origin?: MemoryOrigin;
  originRef?: string;
}

export interface MemorySearchInput {
  userId: string;
  queryText?: string;
  embedding?: number[];
  projectId?: string;
  memoryTypes?: MemoryType[];
  scopes?: MemoryScope[];
  status?: MemoryStatus;
  topK?: number;
  minConfidence?: number;
  minImportance?: number;
  includeExpired?: boolean;
  explain?: boolean;
  /** Point-in-time query: the facts valid at this ISO-8601 instant. */
  asOf?: string;
}

// ── Score Breakdown ─────────────────────────────────────────────

export interface ScoreBreakdown {
  vector_score: number | null;
  recency_score: number;
  importance_score: number;
  authority_score: number;
  confidence_score: number;
  final_score: number;
}

export interface MemorySearchResult {
  memory: Memory;
  score: ScoreBreakdown | null;
}

export interface MemorySearchResponse {
  results: MemorySearchResult[];
  total_candidates: number;
  strategy: string;
}

// ── Events ──────────────────────────────────────────────────────

export type EventType = 'user_message' | 'agent_message' | 'tool_call' | 'tool_result' | 'system_event' | 'observation' | 'reflection';

export interface Event {
  id: string;
  user_id: string;
  run_id: string | null;
  event_type: EventType;
  content: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface EventCreateInput {
  userId: string;
  runId?: string;
  eventType?: EventType;
  content: string;
  metadata?: Record<string, unknown>;
}

// ── Links ───────────────────────────────────────────────────────

export interface MemoryLink {
  id: string;
  source_memory_id: string;
  target_memory_id: string;
  link_type: LinkType;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface LinkCreateInput {
  sourceMemoryId: string;
  targetMemoryId: string;
  linkType: LinkType;
  metadata?: Record<string, unknown>;
}

// ── Health ──────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  version: string;
  database: string;
  embedding_provider: string;
}

// ── Graph ───────────────────────────────────────────────────────

export interface GraphExpandInput {
  memoryId: string;
  maxDepth?: number;
  linkTypes?: LinkType[];
}

// ── Consolidation ───────────────────────────────────────────────

export interface ConsolidateInput {
  userId: string;
  similarityThreshold?: number;
  dryRun?: boolean;
}

export interface ConsolidateResponse {
  duplicates_found: number;
  merged: number;
  details: unknown[];
}

// ── Import/Export ───────────────────────────────────────────────

export interface ExportResponse {
  version: string;
  exported_at: string;
  data: unknown;
}

// ── Forgetting ──────────────────────────────────────────────────

/** One recorded forgetting decision (decay, expiry, or erasure). */
export interface ForgettingLogEntry {
  id: string;
  memory_id: string;
  user_id: string;
  /** decayed | decayed_archive | expired | user_erasure | admin_erasure */
  action: string;
  reason: string | null;
  triggered_by: string | null;
  /** SHA-256 of erased content — proves what was deleted without keeping it. */
  content_hash: string | null;
  occurred_at: string;
}

/** Receipt for a hard erasure (GDPR right-to-be-forgotten). */
export interface ErasureResponse {
  erased: number;
  action: string;
  memory_id: string | null;
  user_id: string | null;
}

// ── Provenance ──────────────────────────────────────────────────

/** Who wrote a fact — the trust domain it entered from. */
export type MemoryOrigin =
  | 'operator'
  | 'user'
  | 'system'
  | 'agent_inference'
  | 'tool_output'
  | 'imported'
  | 'external_ingest';

/** The active write-trust policy. */
export interface OriginPolicy {
  enabled: boolean;
  quarantine_confidence_threshold: number;
  /** origin → highest authority_level that origin may claim */
  authority_ceilings: Record<string, number>;
  untrusted_origins: string[];
}
