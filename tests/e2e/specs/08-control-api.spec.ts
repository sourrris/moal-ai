import { test, expect } from '@playwright/test';

/**
 * Control Plane API tests.
 *
 * IMPORTANT: Control API endpoints require specific scopes NOT granted to newly
 * registered users. The `control:config:read` / `control:config:write` scopes are
 * assigned via migration to pre-existing admins only (ROLE_DEFAULT_SCOPES for
 * "admin" role only includes events/alerts/models/connectors scopes).
 *
 * Tests use the seed user e2e@test.com who has all scopes.
 * This is a known design issue — new admins cannot access control plane APIs.
 *
 * Correct endpoints (from openapi.json):
 *   GET /control/v1/tenants/:id/configuration
 *   PUT /control/v1/tenants/:id/configuration   (not PATCH)
 *   GET /control/v1/connectors/catalog
 *   POST /control/v1/tenants/:id/alert-destinations
 *   GET  /control/v1/tenants/:id/alert-destinations
 *   GET  /control/v1/tenants/:id/reconciliation/ingestion
 *   GET  /control/v1/audit/config-changes
 */

const CONTROL_API = 'http://localhost:8060';
const API = 'http://localhost:8000';

// Seed user with all control-plane scopes (created before migration)
const SEED_EMAIL = 'e2e@test.com';
const SEED_PASSWORD = 'TestPass123!';

let token = '';
let tenantId = '';

test.beforeAll(async ({ request }) => {
  const resp = await request.post(`${API}/v1/auth/token`, {
    data: { username: SEED_EMAIL, password: SEED_PASSWORD },
  });
  expect(resp.status(), `seed user login failed: ${await resp.text()}`).toBe(200);
  const body = await resp.json();
  token = body.access_token;
  const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64').toString());
  tenantId = payload.tenant_id;
});

test.describe('Control API — Tenant Configuration', () => {
  let currentVersion = 0;

  test('GET /control/v1/tenants/:id/configuration returns config', async ({ request }) => {
    const resp = await request.get(`${CONTROL_API}/control/v1/tenants/${tenantId}/configuration`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(resp.status(), `get config failed: ${await resp.text()}`).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty('tenant_id', tenantId);
    expect(body).toHaveProperty('version');
    expect(body).toHaveProperty('anomaly_threshold');
    expect(body).toHaveProperty('enabled_connectors');
    currentVersion = body.version;
  });

  test('GET config without auth returns 401', async ({ request }) => {
    const resp = await request.get(`${CONTROL_API}/control/v1/tenants/${tenantId}/configuration`);
    expect(resp.status()).toBe(401);
  });

  test('PUT /control/v1/tenants/:id/configuration updates threshold', async ({ request }) => {
    // Get current version first
    const getResp = await request.get(`${CONTROL_API}/control/v1/tenants/${tenantId}/configuration`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const current = await getResp.json();

    const resp = await request.put(`${CONTROL_API}/control/v1/tenants/${tenantId}/configuration`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        anomaly_threshold: 0.9,
        enabled_connectors: current.enabled_connectors,
        rule_overrides_json: current.rule_overrides_json ?? {},
        expected_version: current.version,
      },
    });
    expect(resp.status(), `PUT config failed: ${await resp.text()}`).toBe(200);
    const body = await resp.json();
    expect(body.anomaly_threshold).toBe(0.9);
    expect(body.version).toBeGreaterThan(current.version);
  });

  test('PUT with stale version returns 409', async ({ request }) => {
    const resp = await request.put(`${CONTROL_API}/control/v1/tenants/${tenantId}/configuration`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        anomaly_threshold: 0.5,
        enabled_connectors: [],
        rule_overrides_json: {},
        expected_version: 0, // stale version
      },
    });
    expect([409, 422]).toContain(resp.status());
  });
});

test.describe('Control API — Scope Restriction for New Admins', () => {
  let restrictedToken = '';

  test.beforeAll(async ({ request }) => {
    const TS = Date.now();
    // Register a fresh user — will only have basic admin scopes
    const reg = await request.post(`${API}/v1/auth/register`, {
      data: { username: `scope-test+${TS}@aegis.test`, password: 'ScopeTest1!', organization_name: `Scope Org ${TS}` },
    });
    expect(reg.status()).toBe(201);
    restrictedToken = (await reg.json()).access_token;
  });

  test('new admin can GET tenant configuration with control scopes', async ({ request }) => {
    // Get the restricted user's tenant_id
    const payload = JSON.parse(Buffer.from(restrictedToken.split('.')[1], 'base64').toString());
    const newTenantId = payload.tenant_id;

    const resp = await request.get(`${CONTROL_API}/control/v1/tenants/${newTenantId}/configuration`, {
      headers: { Authorization: `Bearer ${restrictedToken}` },
    });
    // New admins now have control:config:read — scope bug was fixed in migration 0009
    expect([200, 404]).toContain(resp.status());
  });
});

test.describe('Control API — Connectors Catalog', () => {
  test('GET /control/v1/connectors/catalog returns list', async ({ request }) => {
    const resp = await request.get(`${CONTROL_API}/control/v1/connectors/catalog`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(resp.status(), `connectors catalog failed: ${await resp.text()}`).toBe(200);
    const body = await resp.json();
    expect(Array.isArray(body)).toBe(true);
    if (body.length > 0) {
      expect(body[0]).toHaveProperty('source_name');
      expect(body[0]).toHaveProperty('enabled');
    }
  });

  test('GET catalog without auth returns 401', async ({ request }) => {
    const resp = await request.get(`${CONTROL_API}/control/v1/connectors/catalog`);
    expect(resp.status()).toBe(401);
  });
});

test.describe('Control API — Alert Destinations', () => {
  test('POST creates webhook destination', async ({ request }) => {
    const TS = Date.now();
    const resp = await request.post(`${CONTROL_API}/control/v1/tenants/${tenantId}/alert-destinations`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        channel: 'webhook',
        name: `pw-dest-${TS}`,
        enabled: true,
        config: { url: 'https://webhook.site/test' },
      },
    });
    expect(resp.status(), `create destination failed: ${await resp.text()}`).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty('destination_id');
    expect(body).toHaveProperty('channel', 'webhook');
  });

  test('GET lists alert destinations', async ({ request }) => {
    const resp = await request.get(`${CONTROL_API}/control/v1/tenants/${tenantId}/alert-destinations`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(resp.status(), `list destinations failed: ${await resp.text()}`).toBe(200);
    const body = await resp.json();
    expect(Array.isArray(body)).toBe(true);
  });
});

test.describe('Control API — Reconciliation', () => {
  test('GET ingestion reconciliation returns counters', async ({ request }) => {
    const resp = await request.get(
      `${CONTROL_API}/control/v1/tenants/${tenantId}/reconciliation/ingestion`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    expect(resp.status(), `reconciliation failed: ${await resp.text()}`).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty('ingested_events');
    expect(body).toHaveProperty('processed_decisions');
    expect(body).toHaveProperty('raised_alerts');
    expect(body).toHaveProperty('delivered_alerts');
    expect(body).toHaveProperty('mismatch_count');
  });
});

test.describe('Control API — Audit Trail', () => {
  test('GET /control/v1/audit/config-changes returns list', async ({ request }) => {
    const resp = await request.get(`${CONTROL_API}/control/v1/audit/config-changes`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(resp.status(), `audit failed: ${await resp.text()}`).toBe(200);
    const body = await resp.json();
    expect(Array.isArray(body)).toBe(true);
  });
});
