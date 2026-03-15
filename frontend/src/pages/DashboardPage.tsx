import { useEffect, useState } from 'react';
import { useApp } from '../context/AppContext';
import StatCard from '../components/StatCard';
import type { SchedulerStatus } from '../lib/types';
import { formatDate } from '../lib/utils';
import { ExternalLink, Play, RefreshCw } from 'lucide-react';

export default function DashboardPage() {
  const { api, connected, health, baseUrl } = useApp();
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [schedError, setSchedError] = useState<string | null>(null);

  useEffect(() => {
    if (!api) return;
    api
      .getSchedulerStatus()
      .then(setScheduler)
      .catch(() => setSchedError('Scheduler not available'));
  }, [api]);

  /* ── Not connected state ────────────────────────────────── */
  if (!connected) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gh-dim">
        <div className="text-5xl mb-4">🧠</div>
        <div className="text-lg mb-2">Welcome to AgentMemoryDB Explorer</div>
        <div className="text-sm">Enter your API URL above and click Connect to get started</div>
      </div>
    );
  }

  /* ── Helpers ─────────────────────────────────────────────── */
  const runJob = async (name: string) => {
    if (!api) return;
    try {
      await api.runJob(name);
      const s = await api.getSchedulerStatus();
      setScheduler(s);
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Error');
    }
  };

  const refreshScheduler = async () => {
    if (!api) return;
    setSchedError(null);
    try {
      setScheduler(await api.getSchedulerStatus());
    } catch {
      setSchedError('Scheduler not available');
    }
  };

  /* ── Render ─────────────────────────────────────────────── */
  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">
      <h1 className="text-lg font-semibold">Dashboard</h1>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard icon="🔌" value={health?.status || 'ok'} label="Status" color="#3fb950" />
        <StatCard icon="📦" value={health?.version || '?'} label="Version" />
        <StatCard
          icon="🗄"
          value={String(health?.database || 'postgres')}
          label="Database"
          color="#8b949e"
        />
        <StatCard
          icon="🧮"
          value={String(health?.embedding_provider || 'n/a')}
          label="Embeddings"
          color="#bc8cff"
        />
      </div>

      {/* Quick links */}
      <div>
        <h2 className="text-xs uppercase tracking-wider text-gh-dim font-semibold mb-3">
          Quick Links
        </h2>
        <div className="flex gap-2 flex-wrap">
          <a
            href={`${baseUrl}/docs`}
            target="_blank"
            rel="noreferrer"
            className="btn-outline btn-sm flex items-center gap-1.5"
          >
            <ExternalLink className="w-3 h-3" /> Swagger UI
          </a>
          <a
            href={`${baseUrl}/redoc`}
            target="_blank"
            rel="noreferrer"
            className="btn-outline btn-sm flex items-center gap-1.5"
          >
            <ExternalLink className="w-3 h-3" /> ReDoc
          </a>
        </div>
      </div>

      {/* Scheduler */}
      <div>
        <h2 className="text-xs uppercase tracking-wider text-gh-dim font-semibold mb-3 flex items-center gap-2">
          Scheduler
          {scheduler && (
            <span className={scheduler.running ? 'text-gh-green' : 'text-gh-red'}>
              — {scheduler.running ? 'Active' : 'Stopped'}
            </span>
          )}
          <button
            className="btn-outline btn-sm ml-2 flex items-center gap-1"
            onClick={refreshScheduler}
          >
            <RefreshCw className="w-3 h-3" /> Refresh
          </button>
        </h2>

        {schedError && (
          <div className="text-xs text-gh-muted bg-gh-canvas border border-gh-border rounded p-3">
            {schedError}
          </div>
        )}

        {scheduler && scheduler.jobs.length > 0 && (
          <div className="bg-gh-canvas border border-gh-border rounded-lg overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gh-dim uppercase tracking-wider text-[9px]">
                  <th className="text-left py-2.5 px-4 border-b border-gh-border">Job</th>
                  <th className="text-left py-2.5 px-4 border-b border-gh-border">Enabled</th>
                  <th className="text-left py-2.5 px-4 border-b border-gh-border">Interval</th>
                  <th className="text-left py-2.5 px-4 border-b border-gh-border">Runs</th>
                  <th className="text-left py-2.5 px-4 border-b border-gh-border">Last Run</th>
                  <th className="text-left py-2.5 px-4 border-b border-gh-border">Actions</th>
                </tr>
              </thead>
              <tbody>
                {scheduler.jobs.map((j) => (
                  <tr key={j.name} className="hover:bg-gh-bg/50">
                    <td className="py-2 px-4 border-b border-gh-border-muted font-medium text-gh-text">
                      {j.name}
                    </td>
                    <td className="py-2 px-4 border-b border-gh-border-muted">
                      {j.enabled ? (
                        <span className="text-gh-green">✓</span>
                      ) : (
                        <span className="text-gh-red">✗</span>
                      )}
                    </td>
                    <td className="py-2 px-4 border-b border-gh-border-muted text-gh-muted">
                      {j.interval_minutes}m
                    </td>
                    <td className="py-2 px-4 border-b border-gh-border-muted text-gh-muted">
                      {j.run_count}
                    </td>
                    <td className="py-2 px-4 border-b border-gh-border-muted text-gh-dim text-[10px]">
                      {formatDate(j.last_run)}
                    </td>
                    <td className="py-2 px-4 border-b border-gh-border-muted">
                      <button
                        className="btn-outline btn-sm flex items-center gap-1"
                        onClick={() => runJob(j.name)}
                      >
                        <Play className="w-3 h-3" /> Run
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
