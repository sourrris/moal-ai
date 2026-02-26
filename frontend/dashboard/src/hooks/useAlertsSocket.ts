import { useEffect, useRef, useState } from 'react';
import type { AlertMessage } from '../types/alert';

const WS_BASE = import.meta.env.VITE_WS_BASE_URL ?? 'http://localhost:8020';

function toWsUrl(baseUrl: string, token: string): string {
  const wsBase = baseUrl.replace(/^http/, 'ws');
  return `${wsBase}/ws/alerts?token=${encodeURIComponent(token)}`;
}

export function useAlertsSocket(token: string | null) {
  const [connected, setConnected] = useState(false);
  const [alerts, setAlerts] = useState<AlertMessage[]>([]);
  const retryRef = useRef<number | null>(null);
  const heartbeatRef = useRef<number | null>(null);

  useEffect(() => {
    if (!token) {
      setConnected(false);
      setAlerts([]);
      return;
    }

    let isActive = true;
    let reconnectDelayMs = 1000;
    let socket: WebSocket | null = null;

    const clearHeartbeat = () => {
      if (heartbeatRef.current) {
        window.clearInterval(heartbeatRef.current);
        heartbeatRef.current = null;
      }
    };

    const connect = () => {
      if (!isActive) {
        return;
      }

      socket = new WebSocket(toWsUrl(WS_BASE, token));

      socket.onopen = () => {
        if (!isActive || !socket) {
          return;
        }
        setConnected(true);
        reconnectDelayMs = 1000;

        clearHeartbeat();
        heartbeatRef.current = window.setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) {
            socket.send('ping');
          }
        }, 20000);
      };

      socket.onmessage = (event) => {
        if (!isActive) {
          return;
        }

        try {
          const parsed = JSON.parse(event.data) as AlertMessage;
          setAlerts((prev) => [parsed, ...prev].slice(0, 200));
        } catch {
          // Ignore malformed payloads to keep dashboard resilient.
        }
      };

      socket.onclose = () => {
        clearHeartbeat();
        if (!isActive) {
          return;
        }
        setConnected(false);
        retryRef.current = window.setTimeout(() => {
          connect();
        }, reconnectDelayMs);
        reconnectDelayMs = Math.min(reconnectDelayMs * 2, 10000);
      };

      socket.onerror = () => {
        socket?.close();
      };
    };

    connect();

    return () => {
      isActive = false;
      clearHeartbeat();
      if (retryRef.current) {
        window.clearTimeout(retryRef.current);
      }
      socket?.close();
    };
  }, [token]);

  return { connected, alerts };
}
