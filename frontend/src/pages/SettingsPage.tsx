import { useApp } from '../context/AppContext';
import { CheckCircle, XCircle } from 'lucide-react';

export default function SettingsPage() {
  const { baseUrl, apiKey, setBaseUrl, setApiKey, connect, connected, health, error } = useApp();

  return (
    <div className="p-6 max-w-xl space-y-6 overflow-y-auto h-full">
      <h1 className="text-lg font-semibold">Settings</h1>

      <div className="space-y-4">
        <div>
          <label className="text-xs uppercase tracking-wider text-gh-dim font-semibold block mb-1.5">
            API Base URL
          </label>
          <input
            className="input-field w-full"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
          />
          <p className="text-[10px] text-gh-dim mt-1">
            The base URL of your AgentMemoryDB instance. Settings are persisted in localStorage.
          </p>
        </div>

        <div>
          <label className="text-xs uppercase tracking-wider text-gh-dim font-semibold block mb-1.5">
            API Key
          </label>
          <input
            className="input-field w-full"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="Optional — leave blank if auth is disabled"
          />
        </div>

        <button className="btn-primary" onClick={connect}>
          Test Connection
        </button>

        {connected && (
          <div className="flex items-center gap-2 text-sm text-gh-green">
            <CheckCircle className="w-4 h-4" />
            Connected — {health?.status} — v{health?.version}
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 text-sm text-gh-red">
            <XCircle className="w-4 h-4" />
            {error}
          </div>
        )}
      </div>

      <div className="pt-4 border-t border-gh-border">
        <h2 className="text-xs uppercase tracking-wider text-gh-dim font-semibold mb-2">About</h2>
        <div className="text-xs text-gh-muted space-y-1">
          <p>
            AgentMemoryDB Explorer is a React-based UI for managing and visualizing agent memories.
          </p>
          <p>Built with Vite · React · TypeScript · Tailwind CSS · D3.js</p>
        </div>
      </div>
    </div>
  );
}
