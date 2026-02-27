import { z } from 'zod';

import { alertListItemSchema } from './alerts';

export const wsAlertPayloadSchema = z.object({
  alert_id: z.string(),
  event_id: z.string(),
  tenant_id: z.string(),
  severity: z.string(),
  model_name: z.string(),
  model_version: z.string(),
  anomaly_score: z.number(),
  threshold: z.number(),
  created_at: z.string()
});

export const wsEnvelopeSchema = z.object({
  type: z.string(),
  occurred_at: z.string(),
  data: wsAlertPayloadSchema
});

export type WsEnvelope<T> = {
  type: 'ALERT_CREATED' | 'CONNECTION_STATUS' | 'MODEL_SWITCHED' | 'SYSTEM_NOTICE';
  occurred_at: string;
  data: T;
};

export type LiveAlertPayload = z.infer<typeof wsAlertPayloadSchema>;

export function normalizeLiveAlert(input: LiveAlertPayload) {
  return alertListItemSchema.parse({
    ...input,
    numeric_alert_id: undefined,
    event_type: 'unknown',
    source: 'live-stream',
    created_at: input.created_at
  });
}
