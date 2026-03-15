import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import type { SearchResult, Memory, Score } from '../lib/types';
import { cn, typeColorClass } from '../lib/utils';
import MemoryDetail from '../components/MemoryDetail';
import { Search, Loader2 } from 'lucide-react';

const TYPES = ['all', 'semantic', 'episodic', 'procedural', 'working'] as const;

export default function ExplorerPage() {
  const { api, connected } = useApp();
  const navigate = useNavigate();

  const [query, setQuery] = useState('');
  const [userId, setUserId] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selected, setSelected] = useState<{ memory: Memory; score?: Score } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = async () => {
    if (!api || !userId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, unknown> = {
        user_id: userId.trim(),
        top_k: 50,
        status: 'active',
      };
      if (query.trim()) params.query_text = query.trim();
      if (typeFilter !== 'all') params.memory_types = [typeFilter];
      const data = await api.searchMemories(params as any);
      setResults(data.results || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Search failed');
    } finally {
      setLoading(false);
    }
  };

  const handleGraphClick = (memoryId: string) => {
    navigate(`/graph?seed=${memoryId}`);
  };

  /* Not connected */
  if (!connected) {
    return (
      <div className="flex items-center justify-center h-full text-gh-dim">
        <div className="text-center">
          <div className="text-4xl mb-3">🔍</div>
          <div>Connect to the API first</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      {/* ── Search sidebar ─────────────────────────────────── */}
      <div className="w-72 border-r border-gh-border flex flex-col shrink-0 bg-gh-canvas">
        <div className="p-3 border-b border-gh-border space-y-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-gh-dim" />
            <input
              className="input-field w-full pl-8"
              placeholder="Search query…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && search()}
            />
          </div>
          <input
            className="input-field w-full"
            placeholder="User ID (required)"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
          />
          <div className="flex flex-wrap gap-1">
            {TYPES.map((t) => (
              <button
                key={t}
                className={cn(
                  'text-[10px] px-2 py-0.5 rounded-full border transition-colors capitalize',
                  typeFilter === t
                    ? 'border-gh-accent text-gh-accent bg-gh-accent-dim'
                    : 'border-gh-border text-gh-dim hover:text-gh-muted',
                )}
                onClick={() => setTypeFilter(t)}
              >
                {t}
              </button>
            ))}
          </div>
          <button
            className="btn-primary w-full text-xs flex items-center justify-center gap-2"
            onClick={search}
            disabled={loading}
          >
            {loading ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <Search className="w-3 h-3" />
            )}
            Search
          </button>
        </div>

        {error && <div className="p-3 text-xs text-gh-red bg-gh-red-dim">{error}</div>}

        {/* Result list */}
        <ul className="flex-1 overflow-y-auto">
          {results.length === 0 && !loading && (
            <div className="flex flex-col items-center justify-center py-12 text-gh-dim">
              <div className="text-3xl mb-2">📭</div>
              <div className="text-xs">No results yet</div>
            </div>
          )}
          {results.map((r) => {
            const m = r.memory;
            const isSelected = selected?.memory.id === m.id;
            return (
              <li
                key={m.id}
                className={cn(
                  'px-3 py-2.5 border-b border-gh-border-muted cursor-pointer transition-colors',
                  isSelected
                    ? 'bg-gh-accent-dim border-l-2 border-l-gh-accent'
                    : 'hover:bg-white/[.02]',
                )}
                onClick={() => setSelected({ memory: m, score: r.score })}
              >
                <div className="text-xs font-medium truncate">{m.memory_key}</div>
                <div className="flex items-center gap-2 mt-1">
                  <span
                    className={cn(
                      'text-[9px] px-1.5 py-0.5 rounded uppercase font-semibold tracking-wide',
                      typeColorClass(m.memory_type),
                    )}
                  >
                    {m.memory_type}
                  </span>
                  <span className="text-[10px] text-gh-dim">v{m.version}</span>
                  {r.score?.final_score != null && (
                    <span className="text-[10px] text-gh-accent ml-auto">
                      {r.score.final_score.toFixed(3)}
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>

        <div className="px-3 py-2 border-t border-gh-border text-[10px] text-gh-dim">
          {results.length} results
        </div>
      </div>

      {/* ── Detail panel ───────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-5">
        {selected ? (
          <MemoryDetail
            memory={selected.memory}
            score={selected.score}
            onGraphClick={handleGraphClick}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-gh-dim">
            <div className="text-4xl mb-3">📋</div>
            <div className="text-sm">Select a memory to view details</div>
          </div>
        )}
      </div>
    </div>
  );
}
