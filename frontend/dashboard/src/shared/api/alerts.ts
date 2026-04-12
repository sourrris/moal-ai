import { z } from 'zod';

import { requestJson } from './http';

export const alertSchema = z.object({
  alert_id: z.string().uuid(),
  event_id: z.string().uuid(),
  severity: z.string(),
  anomaly_score: z.number(),
  threshold: z.number(),
  model_name: z.string(),
  model_version: z.string(),
  state: z.string(),
  user_identifier: z.string(),
  note: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string()
});

export type Alert = z.infer<typeof alertSchema>;

const alertListSchema = z.array(alertSchema);

export async function fetchAlerts(
  token: string,
  state?: string,
  limit = 25,
  offset = 0
) {
  return requestJson('/api/alerts', alertListSchema, {
    token,
    query: { state, limit, offset },
    retries: 2
  });
}

export async function acknowledgeAlert(token: string, alertId: string, note?: string) {
  return requestJson(`/api/alerts/${alertId}/acknowledge`, alertSchema, {
    token,
    method: 'POST',
    body: { note: note ?? null }
  });
}

export async function resolveAlert(token: string, alertId: string, note?: string) {
  return requestJson(`/api/alerts/${alertId}/resolve`, alertSchema, {
    token,
    method: 'POST',
    body: { note: note ?? null }
  });
}

export async function markFalsePositive(token: string, alertId: string, note?: string) {
  return requestJson(`/api/alerts/${alertId}/false-positive`, alertSchema, {
    token,
    method: 'POST',
    body: { note: note ?? null }
  });
}
