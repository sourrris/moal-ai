import { z } from 'zod';

import { requestJson } from './http';

// --- Schemas ---

const modelMetadataSchema = z.object({
  model_name: z.string(),
  model_version: z.string(),
  feature_dim: z.number(),
  threshold: z.number(),
  updated_at: z.string()
});

const trainingRunSchema = z.object({
  run_id: z.string().uuid(),
  model_name: z.string(),
  model_version: z.string().nullable(),
  status: z.string(),
  started_at: z.string(),
  finished_at: z.string().nullable(),
  parameters: z.record(z.any()),
  metrics: z.record(z.any()),
  initiated_by: z.string().nullable()
});

const trainResultSchema = z.object({
  run_id: z.string(),
  status: z.string(),
  model_name: z.string(),
  model_version: z.string(),
  feature_dim: z.number(),
  threshold: z.number(),
  sample_count: z.number(),
  auto_activated: z.boolean(),
  training_metrics: z.record(z.any())
}).passthrough();

const activeModelSchema = z.object({
  active_model: z.record(z.any()).nullable()
});

export type ModelMetadata = z.infer<typeof modelMetadataSchema>;
export type TrainingRun = z.infer<typeof trainingRunSchema>;
export type TrainResult = z.infer<typeof trainResultSchema>;

// --- API Calls ---

export async function fetchMLModels(token: string) {
  return requestJson('/api/models/list', z.array(modelMetadataSchema), { token, retries: 1 });
}

export async function fetchActiveMLModel(token: string) {
  return requestJson('/api/models/active-ml', modelMetadataSchema, { token, retries: 1 });
}

export async function fetchTrainingRuns(token: string, limit = 20) {
  return requestJson('/api/models/training-runs', z.array(trainingRunSchema), {
    token,
    query: { limit },
    retries: 1
  });
}

export async function trainFromHistory(
  token: string,
  params: {
    model_name?: string;
    lookback_hours?: number;
    max_samples?: number;
    epochs?: number;
    batch_size?: number;
    threshold_quantile?: number;
    auto_activate?: boolean;
  }
) {
  return requestJson('/api/models/train', trainResultSchema, {
    token,
    method: 'POST',
    body: params
  });
}

export async function activateModel(token: string, modelName: string, modelVersion: string) {
  return requestJson(
    `/api/models/activate?model_name=${encodeURIComponent(modelName)}&model_version=${encodeURIComponent(modelVersion)}`,
    modelMetadataSchema,
    { token, method: 'POST' }
  );
}
