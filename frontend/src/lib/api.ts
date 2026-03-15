import type {
  HealthResponse,
  SearchResponse,
  Memory,
  MemoryVersion,
  MemoryLink,
  GraphNode,
  SchedulerStatus,
} from './types';

class ApiClient {
  private baseUrl: string;
  private headers: Record<string, string>;

  constructor(baseUrl: string, apiKey?: string) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.headers = { 'Content-Type': 'application/json' };
    if (apiKey) this.headers['X-API-Key'] = apiKey;
  }

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const opts: RequestInit = { method, headers: this.headers };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(`${this.baseUrl}/api/v1${path}`, opts);
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status}: ${text.slice(0, 300)}`);
    }
    return res.json();
  }

  health() {
    return this.request<HealthResponse>('GET', '/health');
  }

  version() {
    return this.request<Record<string, unknown>>('GET', '/version');
  }

  deepHealth() {
    return this.request<Record<string, unknown>>('GET', '/health/deep');
  }

  searchMemories(params: {
    user_id: string;
    query_text?: string;
    memory_types?: string[];
    top_k?: number;
    status?: string;
  }) {
    return this.request<SearchResponse>('POST', '/memories/search', params);
  }

  getMemory(id: string) {
    return this.request<Memory>('GET', `/memories/${id}`);
  }

  getVersions(memoryId: string) {
    return this.request<MemoryVersion[]>('GET', `/memories/${memoryId}/versions`);
  }

  getLinks(memoryId: string) {
    return this.request<MemoryLink[]>('GET', `/memory-links?memory_id=${memoryId}`);
  }

  async expandGraph(memoryId: string, maxHops = 2, maxNodes = 80) {
    const resp = await this.request<{ nodes: GraphNode[] }>(
      'POST',
      '/graph/expand',
      { seed_memory_id: memoryId, max_hops: maxHops, max_nodes: maxNodes },
    );
    return resp.nodes;
  }

  getSchedulerStatus() {
    return this.request<SchedulerStatus>('GET', '/scheduler/status');
  }

  runJob(name: string) {
    return this.request<{ status: string }>('POST', `/scheduler/jobs/${name}/run`);
  }
}

export function createApiClient(baseUrl: string, apiKey?: string) {
  return new ApiClient(baseUrl, apiKey);
}

export type { ApiClient };
