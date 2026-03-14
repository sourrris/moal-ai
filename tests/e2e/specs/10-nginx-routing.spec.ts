import { test, expect } from '@playwright/test';

/**
 * Nginx reverse proxy routing tests.
 * Verifies *.localhost domains route to correct services.
 *
 * Note: DOCTYPE case varies — Vite dev server emits lowercase <!doctype html>
 * but nginx may pass it through unchanged. Tests use case-insensitive matching.
 */

test.describe('Nginx Reverse Proxy', () => {
  test('app.localhost serves the dashboard', async ({ page }) => {
    await page.goto('http://app.localhost');
    await page.waitForLoadState('networkidle');
    const title = await page.title();
    // Dashboard title is "AI Risk Monitor"
    expect(title).toBe('AI Risk Monitor');
  });

  test('api.localhost/docs serves OpenAPI Swagger UI', async ({ request }) => {
    const resp = await request.get('http://api.localhost/docs');
    expect(resp.status()).toBe(200);
    const text = await resp.text();
    // Swagger UI contains "swagger" or "redoc" in HTML
    expect(text.toLowerCase()).toMatch(/swagger|openapi|redoc/i);
  });

  test('api.localhost/health/live proxies to API gateway', async ({ request }) => {
    const resp = await request.get('http://api.localhost/health/live');
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.status).toBe('ok');
    expect(body.service).toBe('api-gateway');
  });

  test('control-api.localhost/health/live proxies to control API', async ({ request }) => {
    const resp = await request.get('http://control-api.localhost/health/live');
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.status).toBe('ok');
    expect(body.service).toBe('control-api');
  });

  test('control.localhost serves control-tenant app', async ({ page }) => {
    await page.goto('http://control.localhost');
    await page.waitForLoadState('domcontentloaded');
    const title = await page.title();
    expect(title).toBe('Aegis Control Console');
  });

  test('ops-control.localhost serves control-ops app', async ({ page }) => {
    await page.goto('http://ops-control.localhost');
    await page.waitForLoadState('domcontentloaded');
    const title = await page.title();
    expect(title).toBe('Aegis Control Ops');
  });

  test('ws.localhost health endpoint is reachable', async ({ request }) => {
    const resp = await request.get('http://ws.localhost/health/live');
    // 200 if proxied to notification service, 426 if WebSocket upgrade required
    expect([200, 426]).toContain(resp.status());
    if (resp.status() === 200) {
      const body = await resp.json();
      expect(body.status).toBe('ok');
    }
  });

  test('api.localhost/openapi.json returns OpenAPI spec', async ({ request }) => {
    const resp = await request.get('http://api.localhost/openapi.json');
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty('openapi');
    expect(body).toHaveProperty('paths');
  });
});
