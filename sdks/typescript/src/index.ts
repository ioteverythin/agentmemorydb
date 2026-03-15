/**
 * @agentmemorydb/sdk — TypeScript client for AgentMemoryDB
 *
 * Inspired by InsForge's multi-language SDK approach.
 * Provides a typed, ergonomic client for all AgentMemoryDB operations.
 *
 * @example
 * ```ts
 * import { AgentMemoryDB } from '@agentmemorydb/sdk';
 *
 * const db = new AgentMemoryDB({
 *   baseUrl: 'http://localhost:8000',
 *   apiKey: 'your-api-key',
 * });
 *
 * // Store a memory
 * const memory = await db.memories.upsert({
 *   userId: 'user-uuid',
 *   memoryKey: 'user_preference_language',
 *   content: 'User prefers Python',
 *   memoryType: 'semantic',
 * });
 *
 * // Recall memories
 * const results = await db.memories.search({
 *   userId: 'user-uuid',
 *   queryText: 'What language does the user prefer?',
 * });
 * ```
 */

export { AgentMemoryDB } from './client';
export type {
  AgentMemoryDBConfig,
  Memory,
  MemoryUpsertInput,
  MemorySearchInput,
  MemorySearchResult,
  MemorySearchResponse,
  Event,
  EventCreateInput,
  MemoryLink,
  LinkCreateInput,
  ScoreBreakdown,
  HealthResponse,
} from './types';
