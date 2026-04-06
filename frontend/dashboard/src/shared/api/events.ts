import { eventsListResponseSchema, type EventsQuery } from '../../entities/events';
import { requestJson } from './http';

export async function fetchEvents(token: string, query: EventsQuery) {
  return requestJson('/api/events', eventsListResponseSchema, {
    token,
    query: query as Record<string, string | number | undefined>,
    retries: 2
  });
}
