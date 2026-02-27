import { z } from 'zod';

export const eventListItemSchema = z.object({
  event_id: z.string(),
  tenant_id: z.string(),
  source: z.string(),
  event_type: z.string(),
  status: z.string(),
  occurred_at: z.string(),
  ingested_at: z.string()
});

export const eventHistoryItemSchema = z.object({
  id: z.number(),
  model_name: z.string(),
  model_version: z.string(),
  anomaly_score: z.number(),
  threshold: z.number(),
  is_anomaly: z.boolean(),
  processed_at: z.string()
});

export const eventDetailSchema = eventListItemSchema.extend({
  payload: z.record(z.any()),
  features: z.array(z.number()),
  submitted_by: z.string(),
  processing_history: z.array(eventHistoryItemSchema)
});

export const eventsListResponseSchema = z.object({
  items: z.array(eventListItemSchema),
  next_cursor: z.string().nullable(),
  total_estimate: z.number()
});

export type EventsQuery = {
  tenant_id?: string;
  status?: string;
  source?: string;
  event_type?: string;
  from?: string;
  to?: string;
  cursor?: string;
  limit?: number;
};

export type EventListItem = z.infer<typeof eventListItemSchema>;
export type EventDetail = z.infer<typeof eventDetailSchema>;
