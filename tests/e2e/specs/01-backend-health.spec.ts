import { test, expect } from '@playwright/test';

/**
 * Backend health checks for all microservices.
 */

const SERVICES: { name: string; url: string }[] = [
  { name: 'API Gateway',         url: 'http://localhost:8000/health/live' },
  { name: 'ML Inference',        url: 'http://localhost:8001/health/live' },
  { name: 'Event Worker',        url: 'http://localhost:8010/health/live' },
  { name: 'Notification Service',url: 'http://localhost:8020/health/live' },
  { name: 'Data Connector',      url: 'http://localhost:8030/health/live' },
  { name: 'Feature Enrichment',  url: 'http://localhost:8040/health/live' },
  { name: 'Metrics Aggregator',  url: 'http://localhost:8050/health/live' },
  { name: 'Control API',         url: 'http://localhost:8060/health/live' },
  { name: 'Alert Router',        url: 'http://localhost:8061/health/live' },
];

const READY_SERVICES: { name: string; url: string }[] = [
  { name: 'API Gateway (ready)',  url: 'http://localhost:8000/health/ready' },
  { name: 'Control API (ready)', url: 'http://localhost:8060/health/ready' },
];

for (const svc of SERVICES) {
  test(`health: ${svc.name} /health/live returns ok`, async ({ request }) => {
    const resp = await request.get(svc.url);
    expect(resp.status(), `${svc.name} not healthy`).toBe(200);
    const body = await resp.json();
    expect(body.status).toBe('ok');
  });
}

for (const svc of READY_SERVICES) {
  test(`readiness: ${svc.name} /health/ready returns ready`, async ({ request }) => {
    const resp = await request.get(svc.url);
    expect(resp.status(), `${svc.name} not ready`).toBe(200);
    const body = await resp.json();
    // /health/ready returns {"status":"ready"} not {"status":"ok"}
    expect(body.status).toBe('ready');
  });
}
