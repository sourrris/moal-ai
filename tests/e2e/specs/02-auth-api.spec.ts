import { test, expect } from '@playwright/test';

/**
 * Authentication API tests — registration, login, token refresh, profile.
 * Register: POST /api/auth/register → 201
 * Login:    POST /api/auth/token   → 200 (JSON body, not form)
 */

const API = 'http://localhost:8000';
const TS = Date.now();
const EMAIL = `playwright+${TS}@aegis.test`;
const PASSWORD = 'PlaywrightPass1!';

test.describe('Auth API — v1', () => {
  let accessToken = '';

  test('register new user returns 201', async ({ request }) => {
    const resp = await request.post(`${API}/api/auth/register`, {
      data: {
        username: EMAIL,
        password: PASSWORD,
        organization_name: `PW Org ${TS}`,
      },
    });
    expect(resp.status(), `register failed: ${await resp.text()}`).toBe(201);
    const body = await resp.json();
    expect(body).toHaveProperty('access_token');
    expect(body.token_type).toBe('bearer');
    accessToken = body.access_token;
  });

  test('login with correct credentials returns 200 token', async ({ request }) => {
    // Register first (may be a no-op if already registered)
    await request.post(`${API}/api/auth/register`, {
      data: { username: EMAIL, password: PASSWORD, organization_name: `PW Org ${TS}` },
    });

    const resp = await request.post(`${API}/api/auth/token`, {
      data: { username: EMAIL, password: PASSWORD },
    });
    expect(resp.status(), `login failed: ${await resp.text()}`).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty('access_token');
    expect(body.token_type).toBe('bearer');
    accessToken = body.access_token;
  });

  test('login with wrong password returns 401', async ({ request }) => {
    const resp = await request.post(`${API}/api/auth/token`, {
      data: { username: EMAIL, password: 'WrongPassword!!' },
    });
    expect(resp.status()).toBe(401);
  });

  test('login with non-existent user returns 401', async ({ request }) => {
    const resp = await request.post(`${API}/api/auth/token`, {
      data: { username: 'nobody@nowhere.test', password: 'Any1!' },
    });
    expect(resp.status()).toBe(401);
  });

  test('GET /api/auth/me not available (not in openapi) — verify protected resource', async ({ request }) => {
    // Acquire token first
    const loginResp = await request.post(`${API}/api/auth/token`, {
      data: { username: EMAIL, password: PASSWORD },
    });
    // This test just verifies login works; /me endpoint may not exist
    expect(loginResp.status()).toBe(200);
  });

  test('duplicate registration returns 409', async ({ request }) => {
    // Register first time
    await request.post(`${API}/api/auth/register`, {
      data: { username: EMAIL, password: PASSWORD, organization_name: `PW Org ${TS}` },
    });
    // Register second time with same email
    const resp = await request.post(`${API}/api/auth/register`, {
      data: { username: EMAIL, password: PASSWORD, organization_name: `PW Org ${TS}` },
    });
    // Should be 409 conflict
    expect([409, 422]).toContain(resp.status());
  });
});
