import { z } from 'zod';

export const modelMetadataSchema = z.object({
  model_name: z.string(),
  model_version: z.string(),
  feature_dim: z.number(),
  threshold: z.number(),
  status: z.string(),
  created_at: z.string()
});

export const modelsListResponseSchema = z.object({
  items: z.array(modelMetadataSchema)
});

export const activeModelSchema = z.object({
  model_name: z.string(),
  model_version: z.string(),
  feature_dim: z.number(),
  threshold: z.number()
});

export const trainingRunSchema = z.object({
  run_id: z.string(),
  model_name: z.string(),
  model_version: z.string().nullable().optional(),
  status: z.string(),
  sample_count: z.number().nullable().optional(),
  epochs: z.number().nullable().optional(),
  train_loss: z.number().nullable().optional(),
  val_loss: z.number().nullable().optional(),
  started_at: z.string(),
  finished_at: z.string().nullable().optional()
});

export const trainingRunsResponseSchema = z.object({
  items: z.array(trainingRunSchema)
});

export const trainResponseSchema = z.object({
  run_id: z.string(),
  status: z.string(),
  model_name: z.string(),
  model_version: z.string().nullable().optional(),
  sample_count: z.number().default(0)
});

export type ModelMetadata = z.infer<typeof modelMetadataSchema>;
export type ActiveModel = z.infer<typeof activeModelSchema>;
export type TrainingRun = z.infer<typeof trainingRunSchema>;
export type TrainResponse = z.infer<typeof trainResponseSchema>;
