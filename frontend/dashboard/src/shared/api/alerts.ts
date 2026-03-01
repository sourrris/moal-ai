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
    event_id: z.string(),
    status: z.string(),
    queued: z.boolean()
  });

  const resolvedTenant = tenantId === 'all' ? 'tenant-alpha' : tenantId;
  const eventSuffix = Math.floor(Math.random() * 1_000_000)
    .toString()
    .padStart(6, '0');
  const idempotencyKey = `dashboard-${resolvedTenant}-${Date.now()}-${eventSuffix}`;

  return requestJson('/v2/events/ingest', ackSchema, {
    method: 'POST',
    token,
    body: {
      idempotency_key: idempotencyKey,
      source: 'dashboard',
      event_type: 'transaction',
      transaction: {
        transaction_id: `txn-${Date.now()}-${eventSuffix}`,
        amount: Number((Math.random() * 15000 + 25).toFixed(2)),
        currency: 'USD',
        source_ip: `198.51.100.${Math.floor(Math.random() * 200) + 1}`,
        source_country: 'US',
        destination_country: Math.random() > 0.7 ? 'GB' : 'US',
        card_bin: '457173',
        card_last4: String(Math.floor(Math.random() * 9000) + 1000),
        merchant_id: `m-${Math.floor(Math.random() * 20) + 1}`,
        merchant_category: 'ecommerce',
        user_email_hash: `hash_${Math.random().toString(16).slice(2, 24).padEnd(16, '0')}`,
        metadata: {
          channel: 'web',
          region: 'us-east-1',
          tenant_hint: resolvedTenant
        }
      },
      occurred_at: new Date().toISOString()
    }
  });
}
