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
  threshold: z.coerce.number().nullable().default(0),
  updated_at: z.string().nullable().default(''),
  inference_count: z.coerce.number().nullable().default(0),
  anomaly_rate: z.coerce.number().nullable().default(0),
  active: z.boolean().default(false),
  activate_capable: z.boolean().default(true),
  source: z.enum(['registry', 'inference_only']).default('registry')
});

export const modelsListResponseSchema = z.object({
  active_model: activeModelSchema.nullable().optional(),
  items: z.array(modelListItemSchema)
});

export const modelMetricsPointSchema = z.object({
  bucket: z.string(),
  avg_threshold: z.coerce.number().nullable().default(0),
  avg_score: z.coerce.number().nullable().default(0),
  volume: z.coerce.number().nullable().default(0)
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

export const modelTrainResponseSchema = z.object({
  run_id: z.string(),
  status: z.string(),
  model_name: z.string(),
  model_version: z.string().nullable().optional(),
  feature_dim: z.coerce.number().nullable().optional(),
  threshold: z.coerce.number().nullable().optional(),
  updated_at: z.string().nullable().optional(),
  training_source: z.enum(['historical_events', 'provided_features']),
  sample_count: z.coerce.number().default(0),
  auto_activated: z.boolean().default(false),
  metrics: z.record(z.any()).default({}),
  error: z.string().nullable().optional()
});

export const modelTrainingRunSchema = z.object({
  run_id: z.string(),
  model_name: z.string(),
  model_version: z.string().nullable().optional(),
  status: z.string(),
  started_at: z.string(),
  finished_at: z.string().nullable().optional(),
  parameters: z.record(z.any()).default({}),
  metrics: z.record(z.any()).default({}),
  initiated_by: z.string().nullable().optional()
});

export const modelTrainingRunsSchema = z.array(modelTrainingRunSchema);

export type ModelListItem = z.infer<typeof modelListItemSchema>;
export type ModelMetrics = z.infer<typeof modelMetricsSchema>;
export type ModelTrainResponse = z.infer<typeof modelTrainResponseSchema>;
export type ModelTrainingRun = z.infer<typeof modelTrainingRunSchema>;
