import { z } from 'zod';

import {
  modelMetricsSchema,
  modelTrainingRunsSchema,
  modelTrainResponseSchema,
  modelsListResponseSchema
} from '../../entities/models';
import { requestJson } from './http';

const metadataSchema = z.object({
  model_name: z.string(),
  model_version: z.string(),
  feature_dim: z.coerce.number(),
  threshold: z.coerce.number(),
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
    tenant_id?: string;
    lookback_hours?: number;
    max_samples?: number;
    min_samples?: number;
    epochs?: number;
    batch_size?: number;
    threshold_quantile?: number;
    auto_activate?: boolean;
  }
) {
  return requestJson('/v1/models/train', modelTrainResponseSchema, {
    method: 'POST',
    token,
    body: {
      model_name: payload.model_name,
      training_source: 'historical_events',
      tenant_id: payload.tenant_id,
      lookback_hours: payload.lookback_hours,
      max_samples: payload.max_samples,
      min_samples: payload.min_samples,
      epochs: payload.epochs,
      batch_size: payload.batch_size,
      threshold_quantile: payload.threshold_quantile,
      auto_activate: payload.auto_activate ?? false
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

export async function fetchTrainingRuns(token: string, modelName?: string) {
  return requestJson('/v1/models/training-runs', modelTrainingRunsSchema, {
    token,
    query: {
      model_name: modelName || undefined,
      limit: 50
    },
    retries: 2
  });
}
