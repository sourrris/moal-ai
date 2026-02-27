import { z } from 'zod';

export const overviewPointSchema = z.object({
  bucket: z.string(),
  avg_score: z.number().nullable().default(0),
  avg_threshold: z.number().nullable().default(0),
  anomaly_count: z.number()
});

export const severityPointSchema = z.object({
  severity: z.string(),
  count: z.number()
});

export const kpiSnapshotSchema = z.object({
  active_anomalies: z.number(),
  alert_rate: z.number(),
  ingestion_rate: z.number(),
  failure_rate: z.number(),
  model_health: z.number(),
  timeseries: z.array(overviewPointSchema),
  severity_distribution: z.array(severityPointSchema)
});

export type KpiSnapshot = z.infer<typeof kpiSnapshotSchema>;
