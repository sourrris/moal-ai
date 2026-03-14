import { test, expect } from '@playwright/test';

/**
 * Control Tenant Console UI tests (http://localhost:5174).
 */

const CONTROL_TENANT = 'http://localhost:5174';
const API = 'http://localhost:8000';
const TS = Date.now();
const EMAIL = `tenant+${TS}@aegis.test`;
const PASSWORD = 'TenantPass1!';

let authToken = '';

test.beforeAll(async ({ request }) => {
  const resp = await request.post(`${API}/v1/auth/register`, {
    data: { username: EMAIL, password: PASSWORD, organization_name: `Tenant Org ${TS}` },
  });
  expect(resp.status(), `register failed: ${await resp.text()}`).toBe(201);
  authToken = (await resp.json()).access_token;
});

test.describe('Control Tenant — Unauthenticated', () => {
  test('shows auth required panel without token', async ({ page }) => {
    await page.goto(CONTROL_TENANT);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000); // wait for session check
    const authMsg = page.locator('[data-testid="auth-required-message"]');
    // Auth panel should show after session check completes
    await expect(authMsg).toBeVisible({ timeout: 8_000 });
  });
});

test.describe('Control Tenant — Authenticated', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((t) => {
      window.localStorage.setItem('risk_token', t);
      window.localStorage.setItem('risk_username', 'tenant@aegis.test');
    }, authToken);
    await page.goto(CONTROL_TENANT);
    await page.waitForLoadState('networkidle');
    // Wait for session check
    await page.waitForTimeout(2000);
  });

  test('workspace app renders without auth-required panel', async ({ page }) => {
    const authMsg = page.locator('[data-testid="auth-required-message"]');
    const count = await authMsg.count();
    expect(count, 'Auth required panel should not show when token is injected').toBe(0);
  });

  test('navigation is visible', async ({ page }) => {
    // Use .first() to avoid strict mode violation (nav may render twice in DOM structure)
    const nav = page.locator('nav.control-nav, nav[aria-label*="Tenant"]').first();
    await expect(nav).toBeVisible({ timeout: 5000 });
  });

  test('workspace overview page loads', async ({ page }) => {
    await page.goto(`${CONTROL_TENANT}/workspace/overview`);
    await page.waitForLoadState('networkidle');
    // Title should mention "Overview"
    await expect(page.locator('h1, h2').first()).toBeVisible({ timeout: 5000 });
  });

  test('connectors config page loads', async ({ page }) => {
    await page.goto(`${CONTROL_TENANT}/workspace/config/connectors`);
    await page.waitForLoadState('networkidle');
    await expect(page.locator('h1, h2, [class*="title"]').first()).toBeVisible({ timeout: 5000 });
  });

  test('risk policy config page has threshold input', async ({ page }) => {
    await page.goto(`${CONTROL_TENANT}/workspace/config/risk-policy`);
    await page.waitForLoadState('networkidle');
    const input = page.locator('#anomaly-threshold');
    await expect(input).toBeVisible({ timeout: 5000 });
  });

  test('model policy config page has model version input', async ({ page }) => {
    await page.goto(`${CONTROL_TENANT}/workspace/config/model-policy`);
    await page.waitForLoadState('networkidle');
    const input = page.locator('#model-version');
    await expect(input).toBeVisible({ timeout: 5000 });
  });

  test('test lab page has event textarea', async ({ page }) => {
    await page.goto(`${CONTROL_TENANT}/workspace/test-lab`);
    await page.waitForLoadState('networkidle');
    const textarea = page.locator('textarea#test-lab-json, textarea').first();
    await expect(textarea).toBeVisible({ timeout: 5000 });
  });

  test('alert routing page has channel selector', async ({ page }) => {
    await page.goto(`${CONTROL_TENANT}/workspace/alert-routing`);
    await page.waitForLoadState('networkidle');
    const select = page.locator('select#destination-channel, select').first();
    await expect(select).toBeVisible({ timeout: 5000 });
  });

  test('reconciliation page loads', async ({ page }) => {
    await page.goto(`${CONTROL_TENANT}/workspace/reconciliation`);
    await page.waitForLoadState('networkidle');
    await expect(page.locator('h1, h2, [class*="title"]').first()).toBeVisible({ timeout: 5000 });
  });
});
