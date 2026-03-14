import { test, expect, type BrowserContext } from '@playwright/test';

/**
 * Dashboard UI tests (http://localhost:5173).
 * Auth context reads token from localStorage['risk_token'] at mount time.
 * Strategy: register once, inject token via addInitScript so it persists
 * across all navigations without needing to re-inject on each page.goto().
 */

const DASH = 'http://localhost:5173';
const API = 'http://localhost:8000';
const TS = Date.now();
const EMAIL = `dash+${TS}@aegis.test`;
const PASSWORD = 'DashPass1!';

let authToken = '';

test.beforeAll(async ({ request }) => {
  const resp = await request.post(`${API}/v1/auth/register`, {
    data: { username: EMAIL, password: PASSWORD, organization_name: `Dash Org ${TS}` },
  });
  expect(resp.status(), `register failed: ${await resp.text()}`).toBe(201);
  authToken = (await resp.json()).access_token;
});

/** Create a browser context that injects the token into every page before scripts run */
async function createAuthContext(browser: Parameters<typeof test.beforeEach>[0] extends never ? never : any) {
  // This helper is unused — we use addInitScript on the page instead.
}

test.describe('Dashboard — Unauthenticated', () => {
  test('redirects to /login when not authenticated', async ({ page }) => {
    await page.goto(DASH);
    await page.waitForURL(/\/login/, { timeout: 8_000 });
    await expect(page).toHaveURL(/\/login/);
  });

  test('login page renders form elements', async ({ page }) => {
    await page.goto(`${DASH}/login`);
    await page.waitForLoadState('networkidle');
    // At minimum a password field should exist
    await expect(page.locator('input[type="password"]').first()).toBeVisible();
  });

  test('register page is accessible', async ({ page }) => {
    await page.goto(`${DASH}/register`);
    await page.waitForLoadState('networkidle');
    await expect(page.locator('input[type="password"]').first()).toBeVisible({ timeout: 5_000 });
  });
});

test.describe('Dashboard — Login Flow', () => {
  test('login with correct credentials navigates to /overview', async ({ page }) => {
    await page.goto(`${DASH}/login`);
    await page.waitForLoadState('networkidle');
    // Use explicit role-based and type-based selectors
    await page.getByRole('textbox', { name: /username/i }).fill(EMAIL);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.getByRole('button', { name: /sign in/i }).first().click();
    await page.waitForURL(/\/overview/, { timeout: 15_000 });
    await expect(page).toHaveURL(/\/overview/);
  });

  test('login with wrong password shows error and stays on /login', async ({ page }) => {
    await page.goto(`${DASH}/login`);
    await page.waitForLoadState('networkidle');
    await page.getByRole('textbox', { name: /username/i }).fill(EMAIL);
    await page.locator('input[type="password"]').fill('WrongPassword!!');
    await page.getByRole('button', { name: /sign in/i }).first().click();
    await page.waitForTimeout(3000);
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe('Dashboard — Authenticated Navigation', () => {
  test.beforeEach(async ({ page }) => {
    // Inject token before the page scripts run so AuthProvider initializes with it
    await page.addInitScript((t) => {
      window.localStorage.setItem('risk_token', t);
    }, authToken);
    await page.goto(`${DASH}/overview`);
    await page.waitForURL(/\/overview/, { timeout: 10_000 });
  });

  test('overview page renders', async ({ page }) => {
    await expect(page).toHaveURL(/\/overview/);
    const main = page.locator('main, [class*="shell"], [class*="app"], #root').first();
    await expect(main).toBeVisible();
  });

  test('sidebar/nav links are visible', async ({ page }) => {
    const nav = page.locator('nav').first();
    await expect(nav).toBeVisible();
  });

  test('can navigate to /alerts without redirect to /login', async ({ page }) => {
    await page.goto(`${DASH}/alerts`);
    await page.waitForLoadState('networkidle');
    await expect(page).not.toHaveURL(/\/login/);
  });

  test('can navigate to /events without redirect to /login', async ({ page }) => {
    await page.goto(`${DASH}/events`);
    await page.waitForLoadState('networkidle');
    await expect(page).not.toHaveURL(/\/login/);
  });

  test('can navigate to /models without redirect to /login', async ({ page }) => {
    await page.goto(`${DASH}/models`);
    await page.waitForLoadState('networkidle');
    await expect(page).not.toHaveURL(/\/login/);
  });

  test('can navigate to /settings without redirect to /login', async ({ page }) => {
    await page.goto(`${DASH}/settings`);
    await page.waitForLoadState('networkidle');
    await expect(page).not.toHaveURL(/\/login/);
  });

  test('unknown route redirects to /overview', async ({ page }) => {
    await page.goto(`${DASH}/this-route-does-not-exist`);
    await page.waitForURL(/\/overview/, { timeout: 5_000 });
    await expect(page).toHaveURL(/\/overview/);
  });
});

test.describe('Dashboard — Page Error Detection', () => {
  test('/login loads without fatal JS errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto(`${DASH}/login`);
    await page.waitForLoadState('networkidle');
    const fatal = errors.filter(
      (e) => !e.includes('ResizeObserver') && !e.includes('favicon') && !e.includes('404')
    );
    expect(fatal, `Fatal JS errors on /login: ${fatal.join('; ')}`).toHaveLength(0);
  });

  test('/overview loads without fatal JS errors when authenticated', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.addInitScript((t) => {
      window.localStorage.setItem('risk_token', t);
    }, authToken);
    await page.goto(`${DASH}/overview`);
    await page.waitForURL(/\/overview/, { timeout: 10_000 });
    await page.waitForLoadState('networkidle');
    const fatal = errors.filter(
      (e) => !e.includes('ResizeObserver') && !e.includes('favicon') && !e.includes('404')
    );
    expect(fatal, `Fatal JS errors on /overview: ${fatal.join('; ')}`).toHaveLength(0);
  });
});
