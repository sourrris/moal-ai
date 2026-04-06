import { z } from 'zod';

export const behaviorEventSchema = z.object({
  event_id: z.string(),
  user_identifier: z.string(),
  event_type: z.string(),
  source: z.string(),
  source_ip: z.string().nullable().optional(),
  user_agent: z.string().nullable().optional(),
  geo_country: z.string().nullable().optional(),
  geo_city: z.string().nullable().optional(),
  session_duration_seconds: z.number().nullable().optional(),
  request_count: z.number().nullable().optional(),
  failed_auth_count: z.number().nullable().optional(),
  bytes_transferred: z.number().nullable().optional(),
  endpoint: z.string().nullable().optional(),
  status_code: z.number().nullable().optional(),
  device_fingerprint: z.string().nullable().optional(),
  anomaly_score: z.number().nullable().optional(),
  is_anomaly: z.boolean().nullable().optional(),
  occurred_at: z.string(),
  created_at: z.string()
});

export const eventsListResponseSchema = z.object({
  items: z.array(behaviorEventSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
  total_pages: z.number()
});

export type EventsQuery = {
  event_type?: string;
  source?: string;
  user_identifier?: string;
  is_anomaly?: boolean;
  page?: number;
  limit?: number;
};

export type BehaviorEvent = z.infer<typeof behaviorEventSchema>;
