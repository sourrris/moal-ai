import { z } from 'zod';

export const alertSchema = z.object({
  alert_id: z.string(),
  event_id: z.string(),
  user_identifier: z.string(),
  severity: z.string(),
  anomaly_score: z.number(),
  threshold: z.number(),
  status: z.string(),
  created_at: z.string(),
  updated_at: z.string().nullable().optional()
});

export const alertsListResponseSchema = z.object({
  items: z.array(alertSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
  total_pages: z.number()
});

export type AlertsQuery = {
  severity?: string;
  status?: string;
  page?: number;
  limit?: number;
};

export type Alert = z.infer<typeof alertSchema>;
