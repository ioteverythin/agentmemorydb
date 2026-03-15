import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import { createApiClient, type ApiClient } from '../lib/api';
import type { HealthResponse } from '../lib/types';

interface AppState {
  baseUrl: string;
  apiKey: string;
  connected: boolean;
  health: HealthResponse | null;
  api: ApiClient | null;
  error: string | null;
  setBaseUrl: (url: string) => void;
  setApiKey: (key: string) => void;
  connect: () => Promise<void>;
}

const AppContext = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [baseUrl, setBaseUrlRaw] = useState(
    () => localStorage.getItem('amdb_baseUrl') || 'http://localhost:8100',
  );
  const [apiKey, setApiKeyRaw] = useState(
    () => localStorage.getItem('amdb_apiKey') || '',
  );
  const [connected, setConnected] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [api, setApi] = useState<ApiClient | null>(null);
  const [error, setError] = useState<string | null>(null);

  const setBaseUrl = useCallback((url: string) => {
    setBaseUrlRaw(url);
    localStorage.setItem('amdb_baseUrl', url);
  }, []);

  const setApiKey = useCallback((key: string) => {
    setApiKeyRaw(key);
    localStorage.setItem('amdb_apiKey', key);
  }, []);

  const connect = useCallback(async () => {
    try {
      setError(null);
      const client = createApiClient(baseUrl, apiKey || undefined);
      const h = await client.health();
      // Also fetch version info for the dashboard
      let merged: HealthResponse = { ...h };
      try {
        const v = await client.version();
        merged = { ...merged, version: String(v.version || '?'), embedding_provider: String(v.embedding_provider || 'n/a'), database: 'postgres', ...v };
      } catch { /* version endpoint optional */ }
      try {
        const d = await client.deepHealth();
        if (d.active_memories && d.active_memories !== 'unavailable') {
          merged.active_memories = String(d.active_memories);
        }
      } catch { /* deep health optional */ }
      setApi(client);
      setHealth(merged);
      setConnected(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Connection failed');
      setConnected(false);
      setApi(null);
      setHealth(null);
    }
  }, [baseUrl, apiKey]);

  return (
    <AppContext.Provider
      value={{ baseUrl, apiKey, connected, health, api, error, setBaseUrl, setApiKey, connect }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used inside AppProvider');
  return ctx;
}
