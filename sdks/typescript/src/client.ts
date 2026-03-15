/**
 * AgentMemoryDB TypeScript Client
 *
 * A fully-typed HTTP client for all AgentMemoryDB API operations.
 * Inspired by InsForge's @insforge/sdk architecture with namespaced
 * sub-clients for each domain (memories, events, graph, etc.).
 */

import type {
  AgentMemoryDBConfig,
  Memory,
  MemoryUpsertInput,
  MemorySearchInput,
  MemorySearchResponse,
  Event,
  EventCreateInput,
  MemoryLink,
  LinkCreateInput,
  GraphExpandInput,
  ConsolidateInput,
  ConsolidateResponse,
  ExportResponse,
  HealthResponse,
} from './types';

// ── HTTP Helper ─────────────────────────────────────────────────

class HttpClient {
  private baseUrl: string;
  private headers: Record<string, string>;
  private timeout: number;

  constructor(config: AgentMemoryDBConfig) {
    this.baseUrl = config.baseUrl.replace(/\/$/, '');
    this.timeout = config.timeout ?? 30000;
    this.headers = {
      'Content-Type': 'application/json',
      ...config.headers,
    };
    if (config.apiKey) {
      this.headers['X-API-Key'] = config.apiKey;
    }
  }

  async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const url = `${this.baseUrl}/api/v1${path}`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(url, {
        method,
        headers: this.headers,
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: response.statusText }));
        throw new AgentMemoryDBError(
          `${method} ${path} failed: ${response.status}`,
          response.status,
          error,
        );
      }

      return response.json() as Promise<T>;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  get<T>(path: string): Promise<T> { return this.request('GET', path); }
  post<T>(path: string, body?: unknown): Promise<T> { return this.request('POST', path, body); }
  put<T>(path: string, body?: unknown): Promise<T> { return this.request('PUT', path, body); }
  patch<T>(path: string, body?: unknown): Promise<T> { return this.request('PATCH', path, body); }
  delete<T>(path: string): Promise<T> { return this.request('DELETE', path); }
}

// ── Error Class ─────────────────────────────────────────────────

export class AgentMemoryDBError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public detail: unknown,
  ) {
    super(message);
    this.name = 'AgentMemoryDBError';
  }
}

// ── Sub-Clients ─────────────────────────────────────────────────

class MemoriesClient {
  constructor(private http: HttpClient) {}

  /** Create or update a memory (versioned, deduplicated). */
  async upsert(input: MemoryUpsertInput): Promise<Memory> {
    return this.http.post('/memories', {
      user_id: input.userId,
      memory_key: input.memoryKey,
      content: input.content,
      memory_type: input.memoryType ?? 'semantic',
      scope: input.scope ?? 'user',
      project_id: input.projectId,
      embedding: input.embedding,
      payload: input.payload,
      source_type: input.sourceType ?? 'agent_inference',
      confidence: input.confidence ?? 0.7,
      importance_score: input.importanceScore ?? 0.5,
      authority_level: input.authorityLevel ?? 1,
      valid_from: input.validFrom,
      valid_to: input.validTo,
      expires_at: input.expiresAt,
      is_contradiction: input.isContradiction ?? false,
    });
  }

  /** Search memories with hybrid scoring (vector + recency + importance + authority + confidence). */
  async search(input: MemorySearchInput): Promise<MemorySearchResponse> {
    return this.http.post('/memories/search', {
      user_id: input.userId,
      query_text: input.queryText,
      embedding: input.embedding,
      project_id: input.projectId,
      memory_types: input.memoryTypes,
      scopes: input.scopes,
      status: input.status ?? 'active',
      top_k: input.topK ?? 10,
      min_confidence: input.minConfidence,
      min_importance: input.minImportance,
      include_expired: input.includeExpired ?? false,
      explain: input.explain ?? false,
    });
  }

  /** Get a specific memory by ID. */
  async get(memoryId: string): Promise<Memory> {
    return this.http.get(`/memories/${memoryId}`);
  }

  /** Update memory status (active, archived, retracted, etc.). */
  async updateStatus(memoryId: string, status: string): Promise<Memory> {
    return this.http.patch(`/memories/${memoryId}/status`, { status });
  }

  /** Get version history for a memory. */
  async versions(memoryId: string): Promise<unknown[]> {
    return this.http.get(`/memories/${memoryId}/versions`);
  }
}

class EventsClient {
  constructor(private http: HttpClient) {}

  /** Record a new event into the memory pipeline. */
  async create(input: EventCreateInput): Promise<Event> {
    return this.http.post('/events', {
      user_id: input.userId,
      run_id: input.runId,
      event_type: input.eventType ?? 'agent_message',
      content: input.content,
      metadata: input.metadata,
    });
  }

  /** List events with optional filters. */
  async list(params?: { userId?: string; runId?: string; limit?: number }): Promise<Event[]> {
    const query = new URLSearchParams();
    if (params?.userId) query.set('user_id', params.userId);
    if (params?.runId) query.set('run_id', params.runId);
    if (params?.limit) query.set('limit', String(params.limit));
    const qs = query.toString();
    return this.http.get(`/events${qs ? `?${qs}` : ''}`);
  }

  /** Get a specific event. */
  async get(eventId: string): Promise<Event> {
    return this.http.get(`/events/${eventId}`);
  }
}

class LinksClient {
  constructor(private http: HttpClient) {}

  /** Create a relationship between two memories. */
  async create(input: LinkCreateInput): Promise<MemoryLink> {
    return this.http.post('/memory-links', {
      source_memory_id: input.sourceMemoryId,
      target_memory_id: input.targetMemoryId,
      link_type: input.linkType,
      metadata: input.metadata,
    });
  }

  /** List links for a memory. */
  async list(memoryId: string): Promise<MemoryLink[]> {
    return this.http.get(`/memory-links?memory_id=${memoryId}`);
  }
}

class GraphClient {
  constructor(private http: HttpClient) {}

  /** BFS expand from a memory node. */
  async expand(input: GraphExpandInput): Promise<Memory[]> {
    return this.http.post('/graph/expand', {
      memory_id: input.memoryId,
      max_depth: input.maxDepth ?? 2,
      link_types: input.linkTypes,
    });
  }

  /** Find shortest path between two memories. */
  async shortestPath(sourceId: string, targetId: string): Promise<unknown> {
    return this.http.post('/graph/shortest-path', {
      source_id: sourceId,
      target_id: targetId,
    });
  }
}

class ConsolidationClient {
  constructor(private http: HttpClient) {}

  /** Find and optionally merge duplicate memories. */
  async consolidate(input: ConsolidateInput): Promise<ConsolidateResponse> {
    return this.http.post('/consolidation/run', {
      user_id: input.userId,
      similarity_threshold: input.similarityThreshold ?? 0.92,
      dry_run: input.dryRun ?? true,
    });
  }
}

class DataClient {
  constructor(private http: HttpClient) {}

  /** Export all data for a user. */
  async export(userId: string): Promise<ExportResponse> {
    return this.http.get(`/data/export?user_id=${userId}`);
  }

  /** Import data from a previous export. */
  async import(data: unknown): Promise<unknown> {
    return this.http.post('/data/import', data);
  }
}

// ── Main Client ─────────────────────────────────────────────────

export class AgentMemoryDB {
  private http: HttpClient;

  /** Memory operations (upsert, search, get, versions). */
  public memories: MemoriesClient;
  /** Event pipeline operations. */
  public events: EventsClient;
  /** Memory relationship management. */
  public links: LinksClient;
  /** Knowledge graph traversal. */
  public graph: GraphClient;
  /** Duplicate detection and merging. */
  public consolidation: ConsolidationClient;
  /** Import/export operations. */
  public data: DataClient;

  constructor(config: AgentMemoryDBConfig) {
    this.http = new HttpClient(config);
    this.memories = new MemoriesClient(this.http);
    this.events = new EventsClient(this.http);
    this.links = new LinksClient(this.http);
    this.graph = new GraphClient(this.http);
    this.consolidation = new ConsolidationClient(this.http);
    this.data = new DataClient(this.http);
  }

  /** Health check. */
  async health(): Promise<HealthResponse> {
    return this.http.get('/health');
  }

  /**
   * Connect to the WebSocket for real-time memory events.
   *
   * @example
   * ```ts
   * const ws = db.realtime(['user:abc-123']);
   * ws.onmessage = (event) => console.log(JSON.parse(event.data));
   * ```
   */
  realtime(channels?: string[]): WebSocket {
    const baseWs = this.http['baseUrl'].replace(/^http/, 'ws');
    const channelParam = channels ? `?channels=${channels.join(',')}` : '';
    return new WebSocket(`${baseWs}/ws${channelParam}`);
  }
}
