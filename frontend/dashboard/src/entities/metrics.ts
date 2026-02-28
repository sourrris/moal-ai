import { z } from 'zod';

export const liveMetricSchema = z.object({
  tenant_id: z.string(),
  event_id: z.string().optional(),
  risk_score: z.number(),
  risk_level: z.string(),
  decision_latency_ms: z.number().optional(),
  occurred_at: z.string().optional(),
  processed_at: z.union([z.string(), z.number()]).optional()
});

export type LiveMetric = z.infer<typeof liveMetricSchema>;
