/* ─── Domain types matching the API schemas ─── */

export interface Memory {
  id: string;
  user_id: string;
  memory_key: string;
  memory_type: 'semantic' | 'episodic' | 'procedural' | 'working';
  content: string;
  scope: string;
  status: 'active' | 'archived' | 'retracted';
  version: number;
  source_type: string;
  authority_level: number;
  confidence: number;
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Score {
  vector_score: number;
  recency_score: number;
  importance_score: number;
  authority_score: number;
  confidence_score: number;
  final_score: number;
}

export interface SearchResult {
  memory: Memory;
  score: Score;
}

export interface SearchResponse {
  results: SearchResult[];
  total?: number;
  query_embedding_time_ms?: number;
  search_time_ms?: number;
}

export interface HealthResponse {
  status: string;
  version: string;
  database: string;
  embedding_provider: string;
  [key: string]: unknown;
}

export interface SchedulerJob {
  name: string;
  enabled: boolean;
  interval_minutes: number;
  run_count: number;
  last_run: string | null;
  errors: number;
}

export interface SchedulerStatus {
  running: boolean;
  jobs: SchedulerJob[];
}

export interface GraphNode {
  memory_id: string;
  memory_key: string;
  memory_type: string;
  content: string;
  depth: number;
  link_type: string;
  link_direction: string;
}

export interface MemoryLink {
  id: string;
  source_memory_id: string;
  target_memory_id: string;
  link_type: string;
  description: string;
  weight: number;
  created_at: string;
}

export interface MemoryVersion {
  version: number;
  content: string;
  created_at: string;
  payload?: Record<string, unknown>;
}

export interface WsEvent {
  id: string;
  event: string;
  data: Record<string, unknown>;
  timestamp: string;
  channel?: string;
}
