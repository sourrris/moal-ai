import { test, expect } from '@playwright/test';
import { randomUUID } from 'crypto';

/**
 * Model management API tests.
 *
 * API Gateway: GET /v1/models (returns {active_model, items[]})
 * ML Service:  GET /v1/models, POST /v1/infer (requires tenant_id + features + event_id UUID)
 */

const API = 'http://localhost:8000';
const ML_API = 'http://localhost:8001';
const TS = Date.now();
const EMAIL = `models+${TS}@aegis.test`;
const PASSWORD = 'ModelsPass1!';

let token = '';
let tenantId = '';

test.beforeAll(async ({ request }) => {
  const reg = await request.post(`${API}/api/auth/register`, {
    data: { username: EMAIL, password: PASSWORD, organization_name: `Models Org ${TS}` },
  });
  expect(reg.status(), `register failed: ${await reg.text()}`).toBe(201);
  const body = await reg.json();
  token = body.access_token;
  const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64').toString());
  tenantId = payload.tenant_id;
});

test.describe('Model Management — API Gateway', () => {
  test('GET /v1/models returns active model and list', async ({ request }) => {
    const resp = await request.get(`${API}/v1/models`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(resp.status(), `models list failed: ${await resp.text()}`).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty('active_model');
    expect(body).toHaveProperty('items');
    expect(Array.isArray(body.items)).toBe(true);
    expect(body.items.length).toBeGreaterThan(0);
    expect(body.active_model).toHaveProperty('model_version');
    expect(body.active_model).toHaveProperty('threshold');
  });

  test('GET /v1/models/active returns active model', async ({ request }) => {
    const resp = await request.get(`${API}/v1/models/active`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty('model_version');
  });

  test('GET /v1/models without auth returns 401', async ({ request }) => {
    const resp = await request.get(`${API}/v1/models`);
    expect(resp.status()).toBe(401);
  });

  test('GET /v1/overview/metrics returns aggregated metrics', async ({ request }) => {
    const resp = await request.get(`${API}/v1/overview/metrics`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect([200, 404]).toContain(resp.status());
    if (resp.status() === 200) {
      const body = await resp.json();
      expect(typeof body).toBe('object');
    }
  });
});

test.describe('Model Management — ML Service', () => {
  test('GET /v1/models returns list of model versions', async ({ request }) => {
    const resp = await request.get(`${ML_API}/v1/models`);
    expect(resp.status()).toBe(200);
    // ML service /v1/models returns an array of model metadata objects
    const body = await resp.json();
    expect(Array.isArray(body)).toBe(true);
    expect(body.length).toBeGreaterThan(0);
    expect(body[0]).toHaveProperty('model_version');
    expect(body[0]).toHaveProperty('threshold');
  });

  test('GET /v1/models/active returns active model metadata', async ({ request }) => {
    const resp = await request.get(`${ML_API}/v1/models/active`);
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty('model_name');
    expect(body).toHaveProperty('model_version');
    expect(body).toHaveProperty('threshold');
  });

  test('POST /v1/infer returns anomaly score', async ({ request }) => {
    const resp = await request.post(`${ML_API}/v1/infer`, {
      data: {
        event_id: randomUUID(),
        tenant_id: tenantId,
        features: [0.01, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.3],
      },
    });
    expect(resp.status(), `infer failed: ${await resp.text()}`).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty('anomaly_score');
    expect(body).toHaveProperty('is_anomaly');
    expect(body).toHaveProperty('model_version');
    expect(typeof body.anomaly_score).toBe('number');
    expect(typeof body.is_anomaly).toBe('boolean');
  });

  test('POST /v1/infer rejects missing tenant_id with 422', async ({ request }) => {
    const resp = await request.post(`${ML_API}/v1/infer`, {
      data: {
        event_id: randomUUID(),
        features: [0.01, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.3],
        // missing tenant_id
      },
    });
    expect(resp.status()).toBe(422);
  });

  test('POST /v1/infer rejects wrong feature dim with 400 or 422', async ({ request }) => {
    const resp = await request.post(`${ML_API}/v1/infer`, {
      data: {
        event_id: randomUUID(),
        tenant_id: tenantId,
        features: [0.1, 0.2, 0.3], // wrong length (expected 8)
      },
    });
    expect([400, 422]).toContain(resp.status());
  });
});
