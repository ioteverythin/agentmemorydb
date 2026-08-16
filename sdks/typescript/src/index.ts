/**
 * @engramdb/sdk — TypeScript client for EngramDB
 *
 * Inspired by InsForge's multi-language SDK approach.
 * Provides a typed, ergonomic client for all EngramDB operations.
 *
 * @example
 * ```ts
 * import { EngramDB } from '@engramdb/sdk';
 *
 * const db = new EngramDB({
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

export { EngramDB } from './client';
export type {
  EngramDBConfig,
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
