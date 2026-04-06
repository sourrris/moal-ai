import { overviewMetricsSchema } from '../../entities/overview';
import { requestJson } from './http';

export async function fetchOverviewMetrics(token: string, window: string) {
  return requestJson('/api/overview', overviewMetricsSchema, {
    token,
    query: { window },
    retries: 2
  });
}
