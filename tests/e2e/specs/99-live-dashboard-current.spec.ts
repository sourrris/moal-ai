import { expect, test } from '@playwright/test';

const DASHBOARD_URL = 'http://localhost:5173';
const ADMIN_USERNAME = 'admin';
const ADMIN_PASSWORD = 'admin123';

test('unauthenticated root redirects to login', async ({ page }) => {
  await page.goto(DASHBOARD_URL);
  await page.waitForURL(/\/login$/, { timeout: 10_000 });
  await expect(page).toHaveURL(/\/login$/);
});

test('login loads the single-page dashboard without API 404s or fatal console errors', async ({ page }) => {
  const apiFailures: string[] = [];
  const consoleErrors: string[] = [];

  page.on('response', (response) => {
    const url = response.url();
    if (!url.startsWith('http://localhost:8000/api/')) {
      return;
    }
    if (response.status() >= 400) {
      apiFailures.push(`${response.status()} ${url}`);
    }
  });

  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text());
    }
  });

  page.on('pageerror', (error) => {
    consoleErrors.push(error.message);
  });

  await page.goto(`${DASHBOARD_URL}/login`);
  await page.getByLabel(/username/i).fill(ADMIN_USERNAME);
  await page.getByLabel(/password/i).fill(ADMIN_PASSWORD);
  await page.getByRole('button', { name: /enter dashboard/i }).click();

  await page.waitForURL((url) => url.pathname === '/', { timeout: 15_000 });
  await expect(page.getByText('Security behavior in one view.')).toBeVisible();
  await expect(page.getByText('Total events')).toBeVisible();
  await expect(page.getByText('Auth failure rate')).toBeVisible();
  await expect(page.getByText('Recent events')).toBeVisible();
  await expect(page.locator('tbody tr').first()).toBeVisible();
  await page.waitForTimeout(1_000);

  const fatalConsoleErrors = consoleErrors.filter(
    (entry) => !entry.includes('favicon') && !entry.includes('Failed to load resource')
  );

  expect(apiFailures, `API failures observed: ${apiFailures.join(', ')}`).toEqual([]);
  expect(fatalConsoleErrors, `Console errors observed: ${fatalConsoleErrors.join(', ')}`).toEqual([]);
  await expect(page.getByText('Unable to load dashboard metrics.')).toHaveCount(0);
  await expect(page.getByText('Unable to load recent events.')).toHaveCount(0);
});
