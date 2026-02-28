import { z } from 'zod';

import { alertListItemSchema } from './alerts';

export const wsAlertPayloadSchema = z.object({
  alert_id: z.string().optional(),
  event_id: z.string(),
  tenant_id: z.string(),
  severity: z.string(),
  model_name: z.string().optional(),
  model_version: z.string().optional(),
  anomaly_score: z.number().optional(),
  risk_score: z.number().optional(),
  threshold: z.number().optional(),
  created_at: z.string()
});

export const wsEnvelopeSchema = z.object({
  type: z.string(),
  occurred_at: z.string(),
  data: wsAlertPayloadSchema
});

export type WsEnvelope<T> = {
  type: 'ALERT_CREATED' | 'ALERT_V2_CREATED' | 'METRIC_UPDATED' | 'CONNECTION_STATUS' | 'MODEL_SWITCHED' | 'SYSTEM_NOTICE';
  occurred_at: string;
  data: T;
};

export type LiveAlertPayload = z.infer<typeof wsAlertPayloadSchema>;

export function normalizeLiveAlert(input: LiveAlertPayload) {
  return alertListItemSchema.parse({
    ...input,
    alert_id: input.alert_id ?? `${input.event_id}-live`,
    anomaly_score: input.anomaly_score ?? input.risk_score ?? 0,
    model_name: input.model_name ?? 'risk_autoencoder',
    model_version: input.model_version ?? 'v2',
    threshold: input.threshold ?? 0,
    numeric_alert_id: undefined,
    event_type: 'unknown',
    source: 'live-stream',
    created_at: input.created_at
  });
}
