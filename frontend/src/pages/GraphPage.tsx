import { useState, useCallback, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import GraphVisualization from '../components/GraphVisualization';
import type { GraphNode } from '../lib/types';
import { Loader2 } from 'lucide-react';

export default function GraphPage() {
  const { api, connected } = useApp();
  const [searchParams] = useSearchParams();

  const [seedId, setSeedId] = useState('');
  const [hops, setHops] = useState(2);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [links, setLinks] = useState<{ source: string; target: string; type: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /* Load graph for a given seed */
  const loadGraph = useCallback(
    async (targetId: string) => {
      if (!api || !targetId) return;
      setLoading(true);
      setError(null);
      try {
        const result = await api.expandGraph(targetId, hops, 80);
        if (!result?.length) {
          setNodes([]);
          setLinks([]);
          setError('No nodes found');
          return;
        }

        const nodeIds = new Set(result.map((n) => n.memory_id));
        const graphLinks: { source: string; target: string; type: string }[] = [];
        result.forEach((n) => {
          if (n.depth > 0 && n.link_direction) {
            const src = n.link_direction === 'outgoing' ? targetId : n.memory_id;
            const tgt = n.link_direction === 'outgoing' ? n.memory_id : targetId;
            if (nodeIds.has(src) && nodeIds.has(tgt)) {
              graphLinks.push({ source: src, target: tgt, type: n.link_type || 'related' });
            }
          }
        });

        setNodes(result);
        setLinks(graphLinks);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load graph');
      } finally {
        setLoading(false);
      }
    },
    [api, hops],
  );

  /* Auto-load from URL ?seed= param */
  useEffect(() => {
    const seed = searchParams.get('seed');
    if (seed) {
      setSeedId(seed);
      loadGraph(seed);
    }
  }, [searchParams, loadGraph]);

  /* Click a node → re-seed on it */
  const handleNodeClick = useCallback(
    (id: string) => {
      setSeedId(id);
      loadGraph(id);
    },
    [loadGraph],
  );

  /* Not connected */
  if (!connected) {
    return (
      <div className="flex items-center justify-center h-full text-gh-dim">
        <div className="text-center">
          <div className="text-4xl mb-3">🕸</div>
          <div>Connect to the API first</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Controls bar */}
      <div className="flex items-center gap-2 px-4 py-2 bg-gh-canvas border-b border-gh-border shrink-0">
        <input
          className="input-field w-64"
          placeholder="Memory ID (seed node)"
          value={seedId}
          onChange={(e) => setSeedId(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && loadGraph(seedId.trim())}
        />
        <select
          className="input-field"
          value={hops}
          onChange={(e) => setHops(parseInt(e.target.value))}
        >
          <option value={1}>1 hop</option>
          <option value={2}>2 hops</option>
          <option value={3}>3 hops</option>
        </select>
        <button
          className="btn-primary btn-sm"
          onClick={() => loadGraph(seedId.trim())}
          disabled={loading}
        >
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Explore'}
        </button>
        <button
          className="btn-outline btn-sm"
          onClick={() => {
            setNodes([]);
            setLinks([]);
            setError(null);
          }}
        >
          Reset
        </button>
        {error && <span className="text-xs text-gh-red ml-2">{error}</span>}
      </div>

      {/* Graph area */}
      <div className="flex-1 relative">
        {nodes.length > 0 ? (
          <GraphVisualization
            nodes={nodes}
            links={links}
            seedId={seedId}
            onNodeClick={handleNodeClick}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-gh-dim">
            <div className="text-5xl mb-4">🕸</div>
            <div className="text-sm">Enter a Memory ID and click Explore</div>
            <div className="text-xs mt-1">to visualize memory connections</div>
          </div>
        )}
      </div>
    </div>
  );
}
