import { useState, useEffect } from 'react';
import type { Memory, Score, MemoryVersion, MemoryLink } from '../lib/types';
import { useApp } from '../context/AppContext';
import { formatDate, formatId, typeColorClass } from '../lib/utils';
import ScoreBar from './ScoreBar';
import { Network, Copy, Clock, Link2 } from 'lucide-react';

interface MemoryDetailProps {
  memory: Memory;
  score?: Score;
  onGraphClick?: (memoryId: string) => void;
}

export default function MemoryDetail({ memory, score, onGraphClick }: MemoryDetailProps) {
  const { api } = useApp();
  const [versions, setVersions] = useState<MemoryVersion[]>([]);
  const [links, setLinks] = useState<MemoryLink[]>([]);

  useEffect(() => {
    if (!api) return;
    api.getVersions(memory.id).then(setVersions).catch(() => setVersions([]));
    api.getLinks(memory.id).then(setLinks).catch(() => setLinks([]));
  }, [api, memory.id]);

  const copyId = () => navigator.clipboard?.writeText(memory.id);

  const statusColor =
    memory.status === 'active'
      ? 'text-gh-green'
      : memory.status === 'archived'
        ? 'text-gh-orange'
        : 'text-gh-red';

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-lg font-semibold">{memory.memory_key}</h2>
          <div className="text-[10px] text-gh-dim font-mono mt-0.5">{memory.id}</div>
        </div>
        <div className="flex gap-2">
          {onGraphClick && (
            <button
              className="btn-outline btn-sm flex items-center gap-1"
              onClick={() => onGraphClick(memory.id)}
            >
              <Network className="w-3 h-3" /> Graph
            </button>
          )}
          <button className="btn-outline btn-sm flex items-center gap-1" onClick={copyId}>
            <Copy className="w-3 h-3" /> Copy ID
          </button>
        </div>
      </div>

      {/* Metadata grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
        {[
          {
            label: 'Type',
            value: (
              <span
                className={`text-xs px-2 py-0.5 rounded font-semibold uppercase ${typeColorClass(memory.memory_type)}`}
              >
                {memory.memory_type}
              </span>
            ),
          },
          { label: 'Scope', value: memory.scope },
          { label: 'Status', value: <span className={statusColor}>{memory.status}</span> },
          { label: 'Version', value: `v${memory.version}` },
          { label: 'Source', value: memory.source_type },
          { label: 'Authority', value: String(memory.authority_level) },
          { label: 'Created', value: formatDate(memory.created_at) },
          { label: 'Updated', value: formatDate(memory.updated_at) },
        ].map((item, i) => (
          <div key={i} className="bg-gh-canvas border border-gh-border rounded p-2.5">
            <div className="text-[9px] uppercase tracking-wider text-gh-dim font-semibold">
              {item.label}
            </div>
            <div className="text-sm text-gh-text mt-1">{item.value}</div>
          </div>
        ))}
      </div>

      {/* Scores */}
      {score && (
        <div>
          <h3 className="text-[10px] uppercase tracking-wider text-gh-dim font-semibold mb-2">
            Scores
          </h3>
          <ScoreBar label="Vector" value={score.vector_score ?? 0} color="#58a6ff" />
          <ScoreBar label="Recency" value={score.recency_score ?? 0} color="#3fb950" />
          <ScoreBar label="Importance" value={score.importance_score ?? 0} color="#d29922" />
          <ScoreBar label="Authority" value={score.authority_score ?? 0} color="#bc8cff" />
          <ScoreBar label="Confidence" value={score.confidence_score ?? 0} color="#39d2c0" />
          <ScoreBar label="Final" value={score.final_score ?? 0} color="#58a6ff" />
        </div>
      )}

      {/* Content */}
      <div>
        <h3 className="text-[10px] uppercase tracking-wider text-gh-dim font-semibold mb-2">
          Content
        </h3>
        <div className="bg-gh-canvas border border-gh-border rounded-lg p-4 text-sm leading-relaxed whitespace-pre-wrap max-h-64 overflow-y-auto">
          {memory.content}
        </div>
      </div>

      {/* Payload */}
      {memory.payload && Object.keys(memory.payload).length > 0 && (
        <div>
          <h3 className="text-[10px] uppercase tracking-wider text-gh-dim font-semibold mb-2">
            Payload
          </h3>
          <div className="bg-gh-canvas border border-gh-border rounded-lg p-4 text-xs font-mono leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto">
            {JSON.stringify(memory.payload, null, 2)}
          </div>
        </div>
      )}

      {/* Version history */}
      {versions.length > 0 && (
        <div>
          <h3 className="text-[10px] uppercase tracking-wider text-gh-dim font-semibold mb-2 flex items-center gap-2">
            <Clock className="w-3 h-3" /> Version History ({versions.length})
          </h3>
          <div className="space-y-2">
            {versions.map((v) => (
              <div
                key={v.version}
                className="bg-gh-canvas border border-gh-border rounded p-3"
              >
                <div className="flex justify-between text-xs">
                  <span className="font-semibold text-gh-accent">v{v.version}</span>
                  <span className="text-gh-dim">{formatDate(v.created_at)}</span>
                </div>
                <div className="text-xs text-gh-muted mt-1.5 whitespace-pre-wrap max-h-20 overflow-hidden">
                  {v.content}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Links */}
      {links.length > 0 && (
        <div>
          <h3 className="text-[10px] uppercase tracking-wider text-gh-dim font-semibold mb-2 flex items-center gap-2">
            <Link2 className="w-3 h-3" /> Links ({links.length})
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gh-dim uppercase tracking-wider text-[9px]">
                  <th className="text-left py-2 px-3 border-b border-gh-border">Type</th>
                  <th className="text-left py-2 px-3 border-b border-gh-border">Source</th>
                  <th className="text-left py-2 px-3 border-b border-gh-border">Target</th>
                  <th className="text-left py-2 px-3 border-b border-gh-border">Description</th>
                </tr>
              </thead>
              <tbody>
                {links.map((l) => (
                  <tr key={l.id} className="hover:bg-gh-bg/50">
                    <td className="py-2 px-3 border-b border-gh-border-muted">
                      <span className="bg-gh-purple-dim text-gh-purple text-[10px] px-1.5 py-0.5 rounded">
                        {l.link_type}
                      </span>
                    </td>
                    <td className="py-2 px-3 border-b border-gh-border-muted font-mono text-gh-muted">
                      {formatId(l.source_memory_id)}
                    </td>
                    <td className="py-2 px-3 border-b border-gh-border-muted font-mono text-gh-muted">
                      {formatId(l.target_memory_id)}
                    </td>
                    <td className="py-2 px-3 border-b border-gh-border-muted text-gh-muted">
                      {l.description || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
