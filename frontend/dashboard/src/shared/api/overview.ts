import { kpiSnapshotSchema } from '../../entities/overview';
import { requestJson } from './http';

export async function fetchOverviewMetrics(token: string, tenantId: string, window: string) {
  return requestJson('/v1/overview/metrics', kpiSnapshotSchema, {
    token,
    query: {
      tenant_id: tenantId === 'all' ? undefined : tenantId,
      window
    }
  });
}
