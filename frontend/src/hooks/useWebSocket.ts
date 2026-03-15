import { useState, useRef, useCallback, useEffect } from 'react';
import type { WsEvent } from '../lib/types';
import { generateId } from '../lib/utils';

interface UseWebSocketOptions {
  baseUrl: string;
  channels?: string;       // comma-separated, e.g. "global,user:abc"
  maxEvents?: number;
}

export function useWebSocket({
  baseUrl,
  channels = 'global',
  maxEvents = 500,
}: UseWebSocketOptions) {
  const [events, setEvents] = useState<WsEvent[]>([]);
  const [status, setStatus] = useState<'disconnected' | 'connecting' | 'connected' | 'error'>(
    'disconnected',
  );
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();

  const addEvent = useCallback(
    (event: string, data: Record<string, unknown>, channel?: string) => {
      const e: WsEvent = {
        id: generateId(),
        event,
        data,
        timestamp: new Date().toISOString(),
        channel,
      };
      setEvents((prev) => [e, ...prev].slice(0, maxEvents));
    },
    [maxEvents],
  );

  const disconnect = useCallback(() => {
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus('disconnected');
  }, []);

  const connect = useCallback(() => {
    disconnect();
    const wsUrl = baseUrl.replace(/^http/, 'ws') + '/ws?channels=' + channels;
    setStatus('connecting');
    try {
      const socket = new WebSocket(wsUrl);
      wsRef.current = socket;

      socket.onopen = () => {
        setStatus('connected');
        addEvent('system', { message: `Connected to ${wsUrl}` });
      };
      socket.onclose = () => {
        setStatus('disconnected');
        addEvent('system', { message: 'Disconnected' });
        // Auto-reconnect after 5 s
        reconnectTimer.current = setTimeout(() => {
          if (wsRef.current === socket) connect();
        }, 5000);
      };
      socket.onerror = () => {
        setStatus('error');
      };
      socket.onmessage = (e) => {
        try {
          const payload = JSON.parse(e.data);
          addEvent(payload.event || 'message', payload.data || payload, payload.channel);
        } catch {
          addEvent('raw', { message: e.data });
        }
      };
    } catch {
      setStatus('error');
    }
  }, [baseUrl, channels, disconnect, addEvent]);

  const clearEvents = useCallback(() => setEvents([]), []);

  useEffect(() => {
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, []);

  return { events, status, connect, disconnect, clearEvents };
}
