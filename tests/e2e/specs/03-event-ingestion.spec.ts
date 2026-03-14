import { test, expect } from '@playwright/test';
import { randomUUID } from 'crypto';

/**
 * Event ingestion API tests.
 *
 * v1 schema: { tenant_id, source, event_type, features[], event_id(uuid), payload, occurred_at }
 * v2 schema: { idempotency_key, source, event_type, transaction{...}, occurred_at }
 */

const API = 'http://localhost:8000';
const TS = Date.now();
const EMAIL = `events+${TS}@aegis.test`;
const PASSWORD = 'EventsPass1!';

let token = '';
let tenantId = '';

test.beforeAll(async ({ request }) => {
  const reg = await request.post(`${API}/v1/auth/register`, {
    data: { username: EMAIL, password: PASSWORD, organization_name: `Events Org ${TS}` },
  });
  expect(reg.status(), `register failed: ${await reg.text()}`).toBe(201);
  const body = await reg.json();
  token = body.access_token;
  // Extract tenant_id from JWT payload
  const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64').toString());
  tenantId = payload.tenant_id;
});

function makeV1Event(suffix = '') {
  return {
    event_id: randomUUID(),
    tenant_id: tenantId,
    source: 'playwright',
    event_type: 'transaction',
    features: [0.01, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.3],
    payload: { channel: 'e2e', suffix },
    occurred_at: new Date().toISOString(),
  };
}

function makeV2Event(idempotencySuffix = '') {
  return {
    idempotency_key: `pw-v2-${TS}-${idempotencySuffix}-${randomUUID().slice(0, 8)}`,
    source: 'playwright',
    event_type: 'transaction',
    transaction: {
      transaction_id: `txn-${TS}-${idempotencySuffix}`,
      amount: 1250.0,
      currency: 'USD',
      source_country: 'US',
      destination_country: 'GB',
      metadata: { channel: 'e2e' },
    },
    occurred_at: new Date().toISOString(),
  };
}

test.describe('Event Ingestion — v1', () => {
  test('POST /v1/events/ingest returns 202 accepted', async ({ request }) => {
    const resp = await request.post(`${API}/v1/events/ingest`, {
      headers: { Authorization: `Bearer ${token}` },
      data: makeV1Event('a'),
    });
    // v1 ingest returns 202 Accepted (queued asynchronously)
    expect(resp.status(), `v1 ingest failed: ${await resp.text()}`).toBe(202);
    const body = await resp.json();
    expect(body).toHaveProperty('event_id');
    expect(body.status).toBe('accepted');
  });

  test('POST /v1/events/ingest without auth returns 401', async ({ request }) => {
    const resp = await request.post(`${API}/v1/events/ingest`, {
      data: makeV1Event('noauth'),
    });
    expect(resp.status()).toBe(401);
  });

  test('POST /v1/events/ingest with wrong feature dim returns 202 or 422', async ({ request }) => {
    const event = { ...makeV1Event('badfeatures'), features: [0.1, 0.2] };
    const resp = await request.post(`${API}/v1/events/ingest`, {
      headers: { Authorization: `Bearer ${token}` },
      data: event,
    });
    // Might accept at ingest layer and fail at ML layer (202), or validate immediately (422)
    expect([202, 422]).toContain(resp.status());
  });
});

test.describe('Event Ingestion — v2', () => {
  test('POST /v2/events/ingest returns 202 accepted', async ({ request }) => {
    const resp = await request.post(`${API}/v2/events/ingest`, {
      headers: { Authorization: `Bearer ${token}` },
      data: makeV2Event('single'),
    });
    // v2 ingest returns 202 Accepted (queued asynchronously)
    expect(resp.status(), `v2 ingest failed: ${await resp.text()}`).toBe(202);
    const body = await resp.json();
    expect(body).toHaveProperty('event_id');
    expect(body.status).toBe('accepted');
  });

  test('POST /v2/events/ingest/batch returns 202', async ({ request }) => {
    const resp = await request.post(`${API}/v2/events/ingest/batch`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { events: [makeV2Event('b1'), makeV2Event('b2')] },
    });
    // Batch returns 202 Accepted (queued asynchronously)
    expect(resp.status(), `v2 batch failed: ${await resp.text()}`).toBe(202);
    const body = await resp.json();
    expect(body).toHaveProperty('accepted');
    expect(body.accepted).toBeGreaterThan(0);
  });

  test('POST /v2/events/ingest without auth returns 401', async ({ request }) => {
    const resp = await request.post(`${API}/v2/events/ingest`, {
      data: makeV2Event('noauth'),
    });
    expect(resp.status()).toBe(401);
  });

  test('POST /v2/events/ingest is idempotent — duplicate key returns status "duplicate"', async ({ request }) => {
    const event = makeV2Event('idem');
    const r1 = await request.post(`${API}/v2/events/ingest`, {
      headers: { Authorization: `Bearer ${token}` },
      data: event,
    });
    expect(r1.status()).toBe(202);
    const b1 = await r1.json();
    expect(b1.status).toBe('accepted');

    // Second call with same idempotency_key — returns 202 with status "duplicate"
    const r2 = await request.post(`${API}/v2/events/ingest`, {
      headers: { Authorization: `Bearer ${token}` },
      data: event,
    });
    expect(r2.status()).toBe(202);
    const b2 = await r2.json();
    expect(b2.status).toBe('duplicate');
  });
});
