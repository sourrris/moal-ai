import { z } from 'zod';

export const overviewMetricsSchema = z.object({
  total_events: z.number(),
  total_alerts: z.number(),
  open_alerts: z.number(),
  avg_anomaly_score: z.number().nullable()
});

export type OverviewMetrics = z.infer<typeof overviewMetricsSchema>;
