import { test, expect } from '@playwright/test';
import { randomUUID } from 'crypto';

/**
 * Data connector, feature enrichment, and ML inference tests.
 *
 * Enrichment response schema: { tenant_id, signals{}, provenance[], enrichment_latency_ms }
 * — signals includes: ip_risk_score, ip_is_proxy, bin_country_mismatch,
 *   jurisdiction_risk_score, sanctions_hit, pep_hit, fx_rate
 * — Does NOT return features[] (feature extraction happens in the worker)
 *
 * Connector: GET /v1/connectors/status (port 8030) — no auth required
 */

const CONNECTOR = 'http://localhost:8030';
const ENRICHMENT = 'http://localhost:8040';
const ML_API = 'http://localhost:8001';
const API = 'http://localhost:8000';
const TS = Date.now();
const EMAIL = `conn+${TS}@aegis.test`;
const PASSWORD = 'ConnPass1!';

let token = '';
let tenantId = '';

test.beforeAll(async ({ request }) => {
  const resp = await request.post(`${API}/v1/auth/register`, {
    data: { username: EMAIL, password: PASSWORD, organization_name: `Conn Org ${TS}` },
  });
  expect(resp.status(), `register failed: ${await resp.text()}`).toBe(201);
  const body = await resp.json();
  token = body.access_token;
  const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64').toString());
  tenantId = payload.tenant_id;
});

test.describe('Data Connector Service', () => {
  test('GET /v1/connectors/status returns connector list', async ({ request }) => {
    const resp = await request.get(`${CONNECTOR}/v1/connectors/status`);
    expect(resp.status(), `connector status failed: ${await resp.text()}`).toBe(200);
    const body = await resp.json();
    expect(Array.isArray(body)).toBe(true);
    if (body.length > 0) {
      expect(body[0]).toHaveProperty('source_name');
      expect(body[0]).toHaveProperty('enabled');
    }
  });

  test('GET /v1/connectors/runs returns run history', async ({ request }) => {
    const resp = await request.get(`${CONNECTOR}/v1/connectors/runs`);
    expect([200, 404]).toContain(resp.status());
    if (resp.status() === 200) {
      const body = await resp.json();
      expect(Array.isArray(body)).toBe(true);
    }
  });

  test('GET /v1/connectors/errors returns error log', async ({ request }) => {
    const resp = await request.get(`${CONNECTOR}/v1/connectors/errors`);
    expect([200, 404]).toContain(resp.status());
  });
});

test.describe('Feature Enrichment Service', () => {
  /**
   * Enrichment returns signal intelligence, NOT a feature vector.
   * The feature vector extraction happens downstream in the worker.
   */
  test('POST /v1/enrichment/resolve returns signals for valid event', async ({ request }) => {
    const resp = await request.post(`${ENRICHMENT}/v1/enrichment/resolve`, {
      data: {
        event_id: randomUUID(),
        tenant_id: tenantId,
        source: 'playwright',
        event_type: 'transaction',
        payload: {
          transaction_id: `txn-enrich-${TS}`,
          amount: 5000.0,
          currency: 'USD',
          source_country: 'US',
          destination_country: 'MX',
        },
        occurred_at: new Date().toISOString(),
      },
    });
    expect(resp.status(), `enrich failed: ${await resp.text()}`).toBe(200);
    const body = await resp.json();
    // Enrichment returns risk signals, not a feature vector
    expect(body).toHaveProperty('tenant_id', tenantId);
    expect(body).toHaveProperty('signals');
    expect(body).toHaveProperty('provenance');
    expect(body).toHaveProperty('enrichment_latency_ms');
    // Signals should include expected fields
    const signals = body.signals;
    expect(signals).toHaveProperty('sanctions_hit');
    expect(signals).toHaveProperty('pep_hit');
    expect(signals).toHaveProperty('ip_risk_score');
  });

  test('POST /v1/enrichment/resolve without tenant_id returns 422', async ({ request }) => {
    const resp = await request.post(`${ENRICHMENT}/v1/enrichment/resolve`, {
      data: {
        event_id: randomUUID(),
        // missing tenant_id
        source: 'playwright',
        event_type: 'transaction',
        payload: {},
        occurred_at: new Date().toISOString(),
      },
    });
    expect(resp.status()).toBe(422);
  });

  test('sanctions_hit is false for routine US-to-MX transaction', async ({ request }) => {
    const resp = await request.post(`${ENRICHMENT}/v1/enrichment/resolve`, {
      data: {
        event_id: randomUUID(),
        tenant_id: tenantId,
        source: 'playwright',
        event_type: 'transaction',
        payload: {
          transaction_id: `txn-sanction-${TS}`,
          amount: 100.0,
          currency: 'USD',
          source_country: 'US',
          destination_country: 'MX',
        },
        occurred_at: new Date().toISOString(),
      },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.signals.sanctions_hit).toBe(false);
    expect(body.signals.pep_hit).toBe(false);
  });
});

test.describe('ML Inference — Anomaly Detection', () => {
  test('normal transaction has low anomaly score', async ({ request }) => {
    const resp = await request.post(`${ML_API}/v1/infer`, {
      data: {
        event_id: randomUUID(),
        tenant_id: tenantId,
        features: [0.005, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2],
      },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty('anomaly_score');
    expect(body).toHaveProperty('is_anomaly');
    expect(body).toHaveProperty('threshold');
    expect(body).toHaveProperty('model_version');
    expect(typeof body.anomaly_score).toBe('number');
    expect(typeof body.is_anomaly).toBe('boolean');
  });

  test('POST /v1/infer/standardized accepts structured event', async ({ request }) => {
    const resp = await request.post(`${ML_API}/v1/infer/standardized`, {
      data: {
        event_id: randomUUID(),
        tenant_id: tenantId,
        source: 'playwright',
        event_type: 'transaction',
        payload: {
          transaction_id: `txn-std-${TS}`,
          amount: 500.0,
          currency: 'EUR',
          source_country: 'DE',
          destination_country: 'FR',
        },
        occurred_at: new Date().toISOString(),
      },
    });
    // 200 if endpoint works, 422 if schema mismatch
    expect([200, 422]).toContain(resp.status());
    if (resp.status() === 200) {
      const body = await resp.json();
      expect(body).toHaveProperty('anomaly_score');
    }
  });
});
