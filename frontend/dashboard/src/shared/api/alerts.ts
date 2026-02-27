import { z } from 'zod';

import { alertDetailSchema, alertsListResponseSchema, type AlertsQuery } from '../../entities/alerts';
import { requestJson } from './http';

export async function fetchAlerts(token: string, query: AlertsQuery) {
  return requestJson('/v1/alerts', alertsListResponseSchema, {
    token,
    query,
    retries: 2
  });
}

export async function fetchAlertDetail(token: string, alertId: string) {
  return requestJson(`/v1/alerts/${alertId}`, alertDetailSchema, {
    token,
    retries: 1
  });
}

export async function ingestSyntheticEvent(token: string, tenantId: string) {
  const ackSchema = z.object({
    status: z.string(),
    event_id: z.string(),
    queued: z.boolean().optional(),
    message: z.string().optional()
  });

  const features = Array.from({ length: 8 }, () => Number((Math.random() * 2 - 1).toFixed(5)));
  return requestJson('/v1/events/ingest', ackSchema, {
    method: 'POST',
    token,
    body: {
      tenant_id: tenantId === 'all' ? 'tenant-alpha' : tenantId,
      source: 'dashboard',
      event_type: 'transaction',
      payload: {
        channel: 'web',
        amount: Math.floor(Math.random() * 15000),
        region: 'us-east-1'
      },
      features
    }
  });
}
