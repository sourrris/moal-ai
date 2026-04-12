import {
  dashboardEventsByHourResponseSchema,
  dashboardEventsByTypeResponseSchema,
  dashboardRecentEventsResponseSchema,
  dashboardStatsSchema,
  dashboardTopUsersResponseSchema
} from '../../entities/overview';
import { requestJson } from './http';

export type DashboardTimeWindow = 'all' | '1h' | '24h' | '7d' | '30d' | 'custom';

export type DashboardFilterParams = {
  window: DashboardTimeWindow;
  startAt?: string;
  endAt?: string;
};

export const DEFAULT_DASHBOARD_FILTERS: DashboardFilterParams = {
  window: 'all'
};

function toDashboardQuery(filters: DashboardFilterParams) {
  return {
    window: filters.window,
    start_at: filters.startAt,
    end_at: filters.endAt
  };
}

export async function fetchDashboardStats(token: string, filters: DashboardFilterParams = DEFAULT_DASHBOARD_FILTERS) {
  return requestJson('/api/dashboard/stats', dashboardStatsSchema, {
    token,
    query: toDashboardQuery(filters),
    retries: 2
  });
}

export async function fetchRecentDashboardEvents(
  token: string,
  filters: DashboardFilterParams = DEFAULT_DASHBOARD_FILTERS,
  limit = 25,
  offset = 0
) {
  return requestJson('/api/dashboard/events/recent', dashboardRecentEventsResponseSchema, {
    token,
    query: { ...toDashboardQuery(filters), limit, offset },
    retries: 2
  });
}

export async function fetchDashboardEventsByType(
  token: string,
  filters: DashboardFilterParams = DEFAULT_DASHBOARD_FILTERS
) {
  return requestJson('/api/dashboard/events/by-type', dashboardEventsByTypeResponseSchema, {
    token,
    query: toDashboardQuery(filters),
    retries: 2
  });
}

export async function fetchDashboardEventsByHour(
  token: string,
  filters: DashboardFilterParams = DEFAULT_DASHBOARD_FILTERS
) {
  return requestJson('/api/dashboard/events/by-hour', dashboardEventsByHourResponseSchema, {
    token,
    query: toDashboardQuery(filters),
    retries: 2
  });
}

export async function fetchDashboardTopUsers(
  token: string,
  filters: DashboardFilterParams = DEFAULT_DASHBOARD_FILTERS,
  limit = 10
) {
  return requestJson('/api/dashboard/users/top', dashboardTopUsersResponseSchema, {
    token,
    query: { ...toDashboardQuery(filters), limit },
    retries: 2
  });
}
