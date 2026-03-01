import { useEffect, useMemo, useRef, useState } from 'react';

import { alertListItemSchema, type AlertListItem } from '../../entities/alerts';
import { liveMetricSchema, type LiveMetric } from '../../entities/metrics';
import { normalizeLiveAlert, wsEnvelopeSchema, systemNoticeSchema, wsAlertPayloadSchema } from '../../entities/websocket';
import type { useToast } from '../ui/toaster';
import { WS_BASE_URL } from '../lib/constants';

function toWsUrl(base: string, token: string, tenant: string) {
  const resolvedTenant = tenant === 'all' ? 'tenant-alpha' : tenant;
  return `${base.replace(/^http/, 'ws')}/ws/risk-stream?channels=alerts,metrics&token=${encodeURIComponent(token)}&tenant_id=${encodeURIComponent(resolvedTenant)}`;
}

export function useRiskStream(token: string | null, tenant: string, toast?: ReturnType<typeof useToast>['toast']) {
  const [connected, setConnected] = useState(false);
  const [stale, setStale] = useState(false);
  const [alerts, setAlerts] = useState<AlertListItem[]>([]);
  const [metrics, setMetrics] = useState<LiveMetric[]>([]);

  const retryRef = useRef<number | null>(null);
  const heartbeatRef = useRef<number | null>(null);
  const staleRef = useRef<number | null>(null);

  useEffect(() => {
    if (!token) {
      setConnected(false);
      setStale(false);
      setAlerts([]);
      setMetrics([]);
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

      socket = new WebSocket(toWsUrl(WS_BASE_URL, token, tenant));
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
        if (event.data === 'pong') {
          return;
        }

        try {
          const raw = JSON.parse(event.data);
          const parsed = wsEnvelopeSchema.safeParse(raw);
          if (parsed.success) {
            if (parsed.data.type === 'ALERT_CREATED' || parsed.data.type === 'ALERT_V2_CREATED') {
              const normalized = normalizeLiveAlert(parsed.data.data);
              console.log(
                `%c[🚨 Live Alert] ${normalized.severity.toUpperCase()}`,
                `color: ${normalized.severity === 'critical' ? '#ef4444' : normalized.severity === 'high' ? '#f97316' : '#eab308'}; font-weight: bold;`,
                normalized
              );
              setAlerts((prev) => [normalized, ...prev].slice(0, 100));
              return;
            }
            if (parsed.data.type === 'METRIC_UPDATED') {
              const metric = liveMetricSchema.safeParse(parsed.data.data);
              if (metric.success) {
                console.debug(
                  `%c[📊 Live Metric]`,
                  'color: #8b5cf6; font-weight: bold;',
                  metric.data
                );
                setMetrics((prev) => [metric.data, ...prev].slice(0, 100));
              }
              return;
            }
            if (parsed.data.type === 'SYSTEM_NOTICE') {
              const notice = systemNoticeSchema.safeParse(parsed.data.data);
              if (notice.success && toast) {
                console.log(
                  `%c[Live Event] ${notice.data.title}`,
                  'color: #0ea5e9; font-weight: bold;',
                  notice.data.message
                );
                toast({
                  title: notice.data.title,
                  description: notice.data.message,
                  type: notice.data.severity === 'info' ? 'info' :
                    notice.data.severity === 'warning' ? 'warning' :
                      notice.data.severity === 'error' ? 'error' : 'success',
                  duration: 6000,
                });
              }
              return;
            }
            return;
          }

          const metricFallback = liveMetricSchema.safeParse(raw);
          if (metricFallback.success) {
            setMetrics((prev) => [metricFallback.data, ...prev].slice(0, 100));
            return;
          }

          const fallback = alertListItemSchema.safeParse(raw);
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
  }, [token, tenant]);

  return useMemo(
    () => ({
      connected,
      stale,
      alerts,
      metrics
    }),
    [alerts, connected, metrics, stale]
  );
}
