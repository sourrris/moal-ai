import { z } from 'zod';

import { alertsListResponseSchema, type AlertsQuery } from '../../entities/alerts';
import { requestJson } from './http';

export async function fetchAlerts(token: string, query: AlertsQuery) {
  return requestJson('/api/alerts', alertsListResponseSchema, {
    token,
    query: query as Record<string, string | number | undefined>,
    retries: 2
  });
}

export async function updateAlertStatus(token: string, alertId: string, status: string) {
  return requestJson(
    `/api/alerts/${alertId}`,
    z.object({ alert_id: z.string(), status: z.string() }),
    {
      method: 'PATCH',
      token,
      body: { status }
    }
  );
}
