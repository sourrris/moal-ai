import {
  activeModelSchema,
  modelsListResponseSchema,
  trainResponseSchema,
  trainingRunsResponseSchema
} from '../../entities/models';
import { requestJson } from './http';

export async function fetchModels(token: string) {
  return requestJson('/api/models', modelsListResponseSchema, { token, retries: 2 });
}

export async function fetchActiveModel(token: string) {
  return requestJson('/api/models/active', activeModelSchema, { token, retries: 2 });
}

export async function fetchTrainingRuns(token: string) {
  return requestJson('/api/models/training-runs', trainingRunsResponseSchema, { token, retries: 2 });
}

export async function trainModel(
  token: string,
  payload: {
    model_name?: string;
    lookback_hours?: number;
    epochs?: number;
    batch_size?: number;
    threshold_quantile?: number;
  }
) {
  return requestJson('/api/models/train', trainResponseSchema, {
    method: 'POST',
    token,
    body: {
      model_name: payload.model_name ?? 'behavior_autoencoder',
      lookback_hours: payload.lookback_hours,
      epochs: payload.epochs,
      batch_size: payload.batch_size,
      threshold_quantile: payload.threshold_quantile
    }
  });
}
