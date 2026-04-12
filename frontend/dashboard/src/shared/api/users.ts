import { z } from 'zod';

import { requestJson } from './http';

const userEventSchema = z.object({
  event_id: z.string().uuid(),
  occurred_at: z.string(),
  event_type: z.string(),
  source: z.string(),
  source_ip: z.string().nullable(),
  geo_country: z.string().nullable(),
  status_code: z.number().nullable(),
  failed_auth_count: z.number(),
  device_fingerprint: z.string().nullable(),
  anomaly_score: z.number().nullable(),
  is_anomaly: z.boolean().nullable(),
  threshold: z.number().nullable()
});

const userProfileSchema = z.object({
  user_identifier: z.string(),
  total_events: z.number(),
  total_anomalies: z.number(),
  first_seen: z.string().nullable(),
  last_seen: z.string().nullable(),
  avg_anomaly_score: z.number().nullable(),
  max_anomaly_score: z.number().nullable(),
  unique_ips: z.number(),
  unique_devices: z.number(),
  unique_countries: z.number(),
  event_types: z.array(z.object({ event_type: z.string(), count: z.number() })),
  hourly_pattern: z.array(z.object({ hour: z.number(), count: z.number() })),
  recent_events: z.array(userEventSchema),
  source_ips: z.array(z.object({ ip: z.string(), count: z.number() })),
  countries: z.array(z.object({ country: z.string(), count: z.number() }))
});

export type UserProfile = z.infer<typeof userProfileSchema>;
export type UserEvent = z.infer<typeof userEventSchema>;

export async function fetchUserProfile(token: string, userIdentifier: string) {
  return requestJson(
    `/api/dashboard/users/${encodeURIComponent(userIdentifier)}/profile`,
    userProfileSchema,
    { token, retries: 2 }
  );
}
