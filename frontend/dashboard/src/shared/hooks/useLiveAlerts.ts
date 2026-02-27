import { useEffect, useMemo, useRef, useState } from 'react';

import { alertListItemSchema, type AlertListItem } from '../../entities/alerts';
import { normalizeLiveAlert, wsEnvelopeSchema } from '../../entities/websocket';
import { WS_BASE_URL } from '../lib/constants';

function toWsUrl(base: string, token: string) {
  return `${base.replace(/^http/, 'ws')}/ws/alerts?token=${encodeURIComponent(token)}`;
}

export function useLiveAlerts(token: string | null) {
  const [connected, setConnected] = useState(false);
  const [stale, setStale] = useState(false);
  const [alerts, setAlerts] = useState<AlertListItem[]>([]);

  const retryRef = useRef<number | null>(null);
  const heartbeatRef = useRef<number | null>(null);
  const staleRef = useRef<number | null>(null);

  useEffect(() => {
    if (!token) {
      setConnected(false);
      setStale(false);
      setAlerts([]);
      return;
    }

    let active = true;
    let socket: WebSocket | null = null;
    let delayMs = 1000;

    const clearTimers = () => {
      if (retryRef.current) window.clearTimeout(retryRef.current);
      if (heartbeatRef.current) window.clearInterval(heartbeatRef.current);
      if (staleRef.current) window.clearTimeout(staleRef.current);
      retryRef.current = null;
      heartbeatRef.current = null;
      staleRef.current = null;
    };

    const markFresh = () => {
      setStale(false);
      if (staleRef.current) window.clearTimeout(staleRef.current);
      staleRef.current = window.setTimeout(() => setStale(true), 45000);
    };

    const connect = () => {
      if (!active) {
        return;
      }

      socket = new WebSocket(toWsUrl(WS_BASE_URL, token));
      socket.onopen = () => {
        if (!active || !socket) return;
        setConnected(true);
        delayMs = 1000;
        markFresh();

        heartbeatRef.current = window.setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) {
            socket.send('ping');
          }
        }, 20000);
      };

      socket.onmessage = (event) => {
        if (!active) return;
        markFresh();

        try {
          const parsed = wsEnvelopeSchema.safeParse(JSON.parse(event.data));
          if (parsed.success && parsed.data.type === 'ALERT_CREATED') {
            const normalized = normalizeLiveAlert(parsed.data.data);
            setAlerts((prev) => [normalized, ...prev].slice(0, 100));
            return;
          }

          const fallback = alertListItemSchema.safeParse(JSON.parse(event.data));
          if (fallback.success) {
            setAlerts((prev) => [fallback.data, ...prev].slice(0, 100));
          }
        } catch {
          // Ignore malformed payloads to preserve socket session.
        }
      };

      socket.onerror = () => {
        socket?.close();
      };

      socket.onclose = () => {
        if (!active) return;
        clearTimers();
        setConnected(false);
        retryRef.current = window.setTimeout(connect, delayMs);
        delayMs = Math.min(delayMs * 2, 10000);
      };
    };

    connect();

    return () => {
      active = false;
      clearTimers();
      socket?.close();
    };
  }, [token]);

  return useMemo(
    () => ({
      connected,
      stale,
      alerts
    }),
    [alerts, connected, stale]
  );
}
