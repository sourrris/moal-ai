import { eventDetailSchema, eventsListResponseSchema, type EventsQuery } from '../../entities/events';
import { requestJson } from './http';

export async function fetchEvents(token: string, query: EventsQuery) {
  return requestJson('/v1/events', eventsListResponseSchema, {
    token,
    query,
    retries: 2
  });
}

export async function fetchEventDetail(token: string, eventId: string) {
  return requestJson(`/v1/events/${eventId}`, eventDetailSchema, {
    token,
    retries: 1
  });
}
