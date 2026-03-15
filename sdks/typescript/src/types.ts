/** Type definitions for the AgentMemoryDB TypeScript SDK. */

// ── Configuration ───────────────────────────────────────────────

export interface AgentMemoryDBConfig {
  /** Base URL of the AgentMemoryDB server */
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
  source_event_id: string | null;
  source_observation_id: string | null;
  source_run_id: string | null;
  status: MemoryStatus;
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
