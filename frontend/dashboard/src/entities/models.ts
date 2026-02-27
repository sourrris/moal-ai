import { z } from 'zod';

export const activeModelSchema = z.object({
  model_name: z.string(),
  model_version: z.string(),
  feature_dim: z.number(),
  threshold: z.number(),
  updated_at: z.string().optional()
});

export const modelListItemSchema = z.object({
  model_name: z.string(),
  model_version: z.string(),
  threshold: z.number().nullable().default(0),
  updated_at: z.string().nullable().default(''),
  inference_count: z.number().nullable().default(0),
  anomaly_rate: z.number().nullable().default(0),
  active: z.boolean().default(false)
});

export const modelsListResponseSchema = z.object({
  active_model: activeModelSchema.partial().default({}),
  items: z.array(modelListItemSchema)
});

export const modelMetricsPointSchema = z.object({
  bucket: z.string(),
  avg_threshold: z.number().nullable().default(0),
  avg_score: z.number().nullable().default(0),
  volume: z.number().nullable().default(0)
});

export const modelMetricsSchema = z.object({
  model_version: z.string(),
  anomaly_hit_rate: z.number(),
  total_inferences: z.number(),
  inference_latency_ms: z.object({
    p50: z.number().nullable(),
    p95: z.number().nullable()
  }),
  threshold_evolution: z.array(modelMetricsPointSchema)
});

export type ModelListItem = z.infer<typeof modelListItemSchema>;
export type ModelMetrics = z.infer<typeof modelMetricsSchema>;
