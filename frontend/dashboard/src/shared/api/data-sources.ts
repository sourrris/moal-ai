import {
  dataSourceRunSummaryListSchema,
  dataSourceStatusListSchema
} from '../../entities/data-sources';
import { requestJson } from './http';

export async function fetchDataSourceStatus(token: string) {
  return requestJson('/v2/data-sources/status', dataSourceStatusListSchema, {
    token,
    retries: 1
  });
}

export async function fetchDataSourceRuns(token: string, limit = 20) {
  return requestJson('/v2/data-sources/runs', dataSourceRunSummaryListSchema, {
    token,
    query: { limit },
    retries: 1
  });
}
