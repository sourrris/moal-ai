import { z } from 'zod';

export const dataSourceStatusSchema = z.object({
  source_name: z.string(),
  enabled: z.boolean(),
  cadence_seconds: z.number().nullable().optional(),
  freshness_slo_seconds: z.number().nullable().optional(),
  latest_status: z.string().nullable(),
  latest_run_at: z.string().nullable(),
  last_success_at: z.string().nullable().optional(),
  last_failure_at: z.string().nullable().optional(),
  freshness_seconds: z.number().nullable(),
  consecutive_failures: z.number(),
  next_run_at: z.string().nullable().optional(),
  degraded_reason: z.string().nullable().optional()
});

export const dataSourceRunSummarySchema = z.object({
  run_id: z.string(),
  source_name: z.string(),
  status: z.string(),
  started_at: z.string(),
  finished_at: z.string().nullable(),
  fetched_records: z.number(),
  upserted_records: z.number(),
  checksum: z.string().nullable(),
  cursor_state: z.record(z.unknown()),
  details: z.record(z.unknown()),
  error_summary: z.record(z.unknown())
});

export const dataSourceStatusListSchema = z.array(dataSourceStatusSchema);
export const dataSourceRunSummaryListSchema = z.array(dataSourceRunSummarySchema);

export type DataSourceStatus = z.infer<typeof dataSourceStatusSchema>;
export type DataSourceRunSummary = z.infer<typeof dataSourceRunSummarySchema>;
