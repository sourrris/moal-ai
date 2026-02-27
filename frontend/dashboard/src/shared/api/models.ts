import { z } from 'zod';

import { modelMetricsSchema, modelsListResponseSchema } from '../../entities/models';
import { requestJson } from './http';

const metadataSchema = z.object({
  model_name: z.string(),
  model_version: z.string(),
  feature_dim: z.number(),
  threshold: z.number(),
  updated_at: z.string().optional()
});

export async function fetchModels(token: string) {
  return requestJson('/v1/models', modelsListResponseSchema, { token, retries: 2 });
}

export async function fetchModelMetrics(token: string, modelVersion: string) {
  return requestJson(`/v1/models/${modelVersion}/metrics`, modelMetricsSchema, { token, retries: 2 });
}

export async function trainModel(
  token: string,
  payload: {
    model_name: string;
    sample_count: number;
    epochs: number;
    batch_size: number;
  }
) {
  const samples = Array.from({ length: payload.sample_count }, () =>
    Array.from({ length: 8 }, () => Number((Math.random() * 2 - 1).toFixed(5)))
  );
  return requestJson('/v1/models/train', metadataSchema, {
    method: 'POST',
    token,
    body: {
      model_name: payload.model_name,
      features: samples,
      epochs: payload.epochs,
      batch_size: payload.batch_size
    }
  });
}

export async function activateModel(token: string, modelName: string, modelVersion: string) {
  return requestJson('/v1/models/activate', metadataSchema, {
    method: 'POST',
    token,
    body: {
      model_name: modelName,
      model_version: modelVersion
    }
  });
}
