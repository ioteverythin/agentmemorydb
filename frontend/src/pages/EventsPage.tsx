import { useApp } from '../context/AppContext';
import { useWebSocket } from '../hooks/useWebSocket';
import { cn, formatDate } from '../lib/utils';
import { Wifi, WifiOff, Trash2 } from 'lucide-react';

const eventIcons: Record<string, { icon: string; cls: string }> = {
  'memory.created': { icon: '➕', cls: 'bg-gh-green-dim text-gh-green' },
  'memory.updated': { icon: '✏️', cls: 'bg-gh-accent-dim text-gh-accent' },
  'memory.archived': { icon: '📦', cls: 'bg-gh-orange-dim text-gh-orange' },
  'memory.retracted': { icon: '🗑', cls: 'bg-gh-red-dim text-gh-red' },
  'memory.linked': { icon: '🔗', cls: 'bg-gh-purple-dim text-gh-purple' },
  'memory.consolidated': { icon: '🔄', cls: 'bg-gh-purple-dim text-gh-purple' },
  'event.recorded': { icon: '📝', cls: 'bg-gh-green-dim text-gh-green' },
  'search.executed': { icon: '🔍', cls: 'bg-gh-cyan-dim text-gh-cyan' },
  'graph.traversed': { icon: '🕸', cls: 'bg-gh-cyan-dim text-gh-cyan' },
  system: { icon: '⚙️', cls: 'bg-gh-border text-gh-muted' },
};

export default function EventsPage() {
  const { baseUrl, connected } = useApp();
  const { events, status, connect, disconnect, clearEvents } = useWebSocket({
    baseUrl,
    channels: 'global',
  });

  const isConnected = status === 'connected';

  return (
    <div className="flex flex-col h-full">
      {/* Header bar */}
      <div className="flex items-center gap-3 px-5 py-3 border-b border-gh-border bg-gh-canvas shrink-0">
        <span
          className={cn(
            'w-2 h-2 rounded-full',
            isConnected ? 'bg-gh-green animate-pulse' : 'bg-gh-dim',
          )}
        />
        <span className="text-xs text-gh-muted">
          {status === 'connected'
            ? 'Connected'
            : status === 'connecting'
              ? 'Connecting…'
              : 'Disconnected'}
        </span>

        <div className="ml-auto flex gap-2">
          {isConnected ? (
            <button
              className="btn-outline btn-sm flex items-center gap-1.5"
              onClick={disconnect}
            >
              <WifiOff className="w-3 h-3" /> Disconnect
            </button>
          ) : (
            <button
              className="btn-primary btn-sm flex items-center gap-1.5"
              onClick={connect}
              disabled={!connected}
            >
              <Wifi className="w-3 h-3" /> Connect
            </button>
          )}
          <button
            className="btn-outline btn-sm flex items-center gap-1.5"
            onClick={clearEvents}
          >
            <Trash2 className="w-3 h-3" /> Clear
          </button>
        </div>
      </div>

      {/* Event feed */}
      <ul className="flex-1 overflow-y-auto px-5">
        {events.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gh-dim">
            <div className="text-4xl mb-3">⚡</div>
            <div className="text-sm">
              {isConnected
                ? 'Waiting for events…'
                : 'Connect WebSocket to see real-time events'}
            </div>
          </div>
        ) : (
          events.map((e) => {
            const ic = eventIcons[e.event] || { icon: '📨', cls: 'bg-gh-border text-gh-muted' };
            return (
              <li
                key={e.id}
                className="flex gap-3 py-2.5 border-b border-gh-border-muted items-start"
              >
                <div
                  className={cn(
                    'w-7 h-7 rounded-full flex items-center justify-center text-xs shrink-0',
                    ic.cls,
                  )}
                >
                  {ic.icon}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-semibold">{e.event}</div>
                  <div className="text-[11px] text-gh-muted truncate mt-0.5">
                    {JSON.stringify(e.data).slice(0, 120)}
                  </div>
                  <div className="text-[10px] text-gh-dim mt-0.5">{formatDate(e.timestamp)}</div>
                </div>
              </li>
            );
          })
        )}
      </ul>

      {/* Footer */}
      <div className="px-5 py-2 border-t border-gh-border text-[10px] text-gh-dim">
        {events.length} events
      </div>
    </div>
  );
}
