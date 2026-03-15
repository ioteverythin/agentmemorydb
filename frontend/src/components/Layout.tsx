import { Outlet, NavLink } from 'react-router-dom';
import { LayoutDashboard, Search, Network, Zap, Settings, Brain } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { cn } from '../lib/utils';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard', end: true },
  { to: '/search', icon: Search, label: 'Explorer', end: false },
  { to: '/graph', icon: Network, label: 'Graph', end: false },
  { to: '/events', icon: Zap, label: 'Events', end: false },
  { to: '/settings', icon: Settings, label: 'Settings', end: false },
];

export default function Layout() {
  const { connected, health, baseUrl, apiKey, setBaseUrl, setApiKey, connect, error } = useApp();

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* ── Header ─────────────────────────────────────────── */}
      <header className="bg-gh-canvas border-b border-gh-border px-6 h-12 flex items-center gap-4 shrink-0">
        <div className="flex items-center gap-2">
          <Brain className="w-5 h-5 text-gh-accent" />
          <span className="font-semibold text-[15px] text-gh-accent">AgentMemoryDB</span>
          <span className="text-[10px] bg-gh-accent text-gh-bg px-2 py-0.5 rounded-full font-bold tracking-wide">
            EXPLORER
          </span>
        </div>

        <div className="flex items-center gap-2 ml-6 flex-1">
          <input
            className="input-field w-56"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="API Base URL"
          />
          <input
            className="input-field w-40"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="API Key (optional)"
          />
          <button className="btn-primary btn-sm" onClick={connect}>
            Connect
          </button>
        </div>

        <div
          className={cn(
            'text-xs flex items-center gap-2',
            connected ? 'text-gh-green' : error ? 'text-gh-red' : 'text-gh-dim',
          )}
        >
          <span
            className={cn(
              'w-2 h-2 rounded-full',
              connected ? 'bg-gh-green' : error ? 'bg-gh-red' : 'bg-gh-dim',
            )}
          />
          {connected
            ? `Connected — ${health?.status || 'ok'}`
            : error
              ? error.slice(0, 40)
              : 'Not connected'}
        </div>
      </header>

      {/* ── Body ───────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar nav */}
        <nav className="w-14 bg-gh-canvas border-r border-gh-border flex flex-col items-center py-3 gap-1 shrink-0">
          {navItems.map(({ to, icon: Icon, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'w-10 h-10 flex items-center justify-center rounded-lg transition-colors group relative',
                  isActive
                    ? 'bg-gh-accent-dim text-gh-accent'
                    : 'text-gh-dim hover:text-gh-muted hover:bg-gh-surface',
                )
              }
              title={label}
            >
              <Icon className="w-[18px] h-[18px]" />
              <span className="absolute left-12 bg-gh-canvas border border-gh-border text-gh-text text-xs px-2 py-1 rounded opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 shadow-lg transition-opacity">
                {label}
              </span>
            </NavLink>
          ))}
        </nav>

        {/* Main content */}
        <main className="flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
