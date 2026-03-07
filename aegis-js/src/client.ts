import type { EventIngestResult, PlatformAlertList, PlatformConfig, PlatformIngestRequest } from './types';

export type AegisClientOptions = {
  baseUrl: string;
  getJwt: () => string | null;
};

export class AegisClient {
  private readonly baseUrl: string;
  private readonly getJwt: () => string | null;

  constructor(options: AegisClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, '');
    this.getJwt = options.getJwt;
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const jwt = this.getJwt();
    const headers = new Headers(init?.headers ?? {});
    headers.set('Content-Type', 'application/json');
    if (jwt) {
      headers.set('Authorization', `Bearer ${jwt}`);
    }

    const response = await fetch(`${this.baseUrl}${path}`, { ...init, headers });
    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Aegis API request failed (${response.status}): ${body}`);
    }
    return (await response.json()) as T;
  }

  ingest(request: PlatformIngestRequest): Promise<EventIngestResult> {
    return this.request<EventIngestResult>('/api/v1/ingest', {
      method: 'POST',
      body: JSON.stringify(request)
    });
  }

  alerts(params: { state?: string; cursor?: string; limit?: number } = {}): Promise<PlatformAlertList> {
    const query = new URLSearchParams();
    if (params.state) query.set('state', params.state);
    if (params.cursor) query.set('cursor', params.cursor);
    if (params.limit) query.set('limit', String(params.limit));
    const suffix = query.toString() ? `?${query.toString()}` : '';
    return this.request<PlatformAlertList>(`/api/v1/alerts${suffix}`);
  }

  metrics(window: '1h' | '24h' | '7d' = '24h'): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(`/api/v1/metrics?window=${window}`);
  }

  config(): Promise<PlatformConfig> {
    return this.request<PlatformConfig>('/api/v1/config');
  }
}
