import { z } from 'zod';

export const dashboardEventTypeSchema = z.object({
  event_type: z.string(),
  count: z.number()
});

export const dashboardEventHourSchema = z.object({
  hour: z.number(),
  count: z.number()
});

export const dashboardTopUserSchema = z.object({
  user_identifier: z.string(),
  event_count: z.number(),
  anomaly_count: z.number(),
  last_seen_at: z.string()
});

export const dashboardGeoSchema = z.object({
  geo_country: z.string(),
  count: z.number()
});

export const dashboardStatsSchema = z.object({
  window: z.string(),
  range_start: z.string().nullable(),
  range_end: z.string().nullable(),
  generated_at: z.string(),
  total_events: z.number(),
  total_alerts: z.number(),
  open_alerts: z.number(),
  avg_anomaly_score: z.number().nullable(),
  auth_failure_rate: z.number(),
  events_by_type: z.array(dashboardEventTypeSchema),
  events_by_hour: z.array(dashboardEventHourSchema),
  top_users: z.array(dashboardTopUserSchema),
  geo_distribution: z.array(dashboardGeoSchema)
});

export const dashboardRecentEventSchema = z.object({
  event_id: z.string().uuid(),
  occurred_at: z.string(),
  user_identifier: z.string(),
  event_type: z.string(),
  source: z.string(),
  source_ip: z.string().nullable(),
  geo_country: z.string().nullable(),
  status_code: z.number().nullable(),
  failed_auth_count: z.number(),
  anomaly_score: z.number().nullable(),
  is_anomaly: z.boolean().nullable()
});

export const dashboardRecentEventsResponseSchema = z.object({
  items: z.array(dashboardRecentEventSchema),
  limit: z.number(),
  offset: z.number()
});

export const dashboardEventsByTypeResponseSchema = z.array(dashboardEventTypeSchema);
export const dashboardEventsByHourResponseSchema = z.array(dashboardEventHourSchema);
export const dashboardTopUsersResponseSchema = z.array(dashboardTopUserSchema);

export type DashboardStats = z.infer<typeof dashboardStatsSchema>;
export type DashboardRecentEventsResponse = z.infer<typeof dashboardRecentEventsResponseSchema>;
