import { z } from 'zod';

export const alertListItemSchema = z.object({
  alert_id: z.string(),
  numeric_alert_id: z.number().optional(),
  event_id: z.string(),
  tenant_id: z.string(),
  event_type: z.string().optional(),
  source: z.string().optional(),
  severity: z.string(),
  model_name: z.string(),
  model_version: z.string(),
  anomaly_score: z.number(),
  threshold: z.number(),
  created_at: z.string()
});

export const alertDetailSchema = alertListItemSchema.extend({
  is_anomaly: z.boolean().optional(),
  event_payload: z.record(z.any()).optional(),
  event_status: z.string().optional(),
  occurred_at: z.string().optional()
});

export const alertsListResponseSchema = z.object({
  items: z.array(alertListItemSchema),
  next_cursor: z.string().nullable(),
  total_estimate: z.number()
});

export type AlertsQuery = {
  tenant_id?: string;
  severity?: string;
  model_version?: string;
  from?: string;
  to?: string;
  score_min?: number;
  score_max?: number;
  cursor?: string;
  limit?: number;
};

export type AlertListItem = z.infer<typeof alertListItemSchema>;
export type AlertDetail = z.infer<typeof alertDetailSchema>;
