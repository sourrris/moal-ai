import { expect, test } from '@playwright/test';

const CONTROL_API_BASE_URL = 'http://control-api.localhost';

function createJwt(scopes: string[], tenantId = 'all'): string {
  const encoded = Buffer.from(
    JSON.stringify({
      tenant_id: tenantId,
      scopes
    })
  ).toString('base64url');
  return `header.${encoded}.signature`;
}

async function seedSession(page: Parameters<typeof test>[0]['page'], scopes: string[]) {
  await page.addInitScript(
    ([token, username]) => {
      window.localStorage.setItem('risk_token', token);
      window.localStorage.setItem('risk_username', username);
    },
    [createJwt(scopes), 'ops@example.com']
  );
}

test.describe('ops control console', () => {
  test('shows the auth-required shell when no session exists', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByText('Aegis Operations Console')).toBeVisible();
    await expect(page.getByText('Playwright Preflight')).toBeVisible();
    await expect(page.getByTestId('auth-required-message')).toContainText('Sign in through the monitoring app first');
    await expect(page.getByRole('link', { name: 'Open Monitoring Login' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Open Tenant Console' })).toBeVisible();
  });

  test('navigates authenticated routes with mocked control-api responses', async ({ page }) => {
    await seedSession(page, [
      'control:tenants:read',
      'control:tenants:write',
      'control:config:read',
      'control:config:write',
      'control:routing:read'
    ]);

    await page.route(`${CONTROL_API_BASE_URL}/control/v1/tenants`, async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            tenant_id: 'tenant-gamma',
            display_name: 'Gamma Bank',
            status: 'active',
            tier: 'standard',
            metadata_json: {},
            created_at: '2026-03-07T00:00:00Z',
            updated_at: '2026-03-07T00:00:00Z'
          })
        });
        return;
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            tenant_id: 'tenant-alpha',
            display_name: 'Alpha Bank',
            status: 'active',
            tier: 'enterprise',
            metadata_json: {},
            created_at: '2026-03-07T00:00:00Z',
            updated_at: '2026-03-07T00:00:00Z'
          }
        ])
      });
    });

    await page.route(`${CONTROL_API_BASE_URL}/control/v1/tenants/*`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          tenant_id: 'tenant-alpha',
          display_name: 'Alpha Bank',
          status: 'suspended',
          tier: 'enterprise',
          metadata_json: {},
          created_at: '2026-03-07T00:00:00Z',
          updated_at: '2026-03-07T00:00:00Z'
        })
      });
    });

    await page.route(`${CONTROL_API_BASE_URL}/control/v1/connectors/catalog`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            source_name: 'ofac_sls',
            source_type: 'sanctions',
            enabled: true,
            cadence_seconds: 3600,
            latest_status: 'ok',
            latest_run_at: '2026-03-07T00:00:00Z'
          }
        ])
      });
    });

    await page.route(`${CONTROL_API_BASE_URL}/control/v1/connectors/*/*`, async (route) => {
      const sourceName = route.request().url().split('/').slice(-2, -1)[0];
      const enabled = route.request().url().endsWith('/global-enable');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok', source_name: sourceName, enabled })
      });
    });

    await page.route(`${CONTROL_API_BASE_URL}/control/v1/delivery/logs*`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            delivery_id: 'delivery-1',
            tenant_id: 'tenant-alpha',
            channel: 'email',
            alert_key: 'alert-1',
            status: 'delivered',
            attempt_no: 1,
            payload_json: {},
            is_test: false,
            attempted_at: '2026-03-07T00:00:00Z'
          }
        ])
      });
    });

    await page.route(`${CONTROL_API_BASE_URL}/control/v1/audit/config-changes*`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 1,
            tenant_id: 'tenant-alpha',
            actor: 'ops@example.com',
            action: 'update',
            resource_type: 'tenant',
            before_json: {},
            after_json: {},
            created_at: '2026-03-07T00:00:00Z'
          }
        ])
      });
    });

    await page.goto('/');

    await expect(page.getByText('Aegis Operations Console')).toBeVisible();
    await expect(page.getByText('Session Capabilities')).toBeVisible();
    await expect(page.getByText('Tenant Operations')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Tenants' })).toBeVisible();
    await expect(page.getByText('Alpha Bank')).toBeVisible();

    await page.getByRole('link', { name: 'Connectors' }).click();
    await expect(page.getByText('Global Connector Operations')).toBeVisible();
    await expect(page.getByText('ofac_sls')).toBeVisible();

    await page.getByRole('link', { name: 'Delivery' }).click();
    await expect(page.getByText('Cross-Tenant Delivery Logs')).toBeVisible();
    await expect(page.getByText('delivered')).toBeVisible();

    await page.getByRole('link', { name: 'Audit' }).click();
    await expect(page.getByText('Configuration Audit Trail')).toBeVisible();
    await expect(page.getByText('ops@example.com')).toBeVisible();
  });

  test('shows visible error state when the control API fails', async ({ page }) => {
    await seedSession(page, ['control:tenants:read']);

    await page.route(`${CONTROL_API_BASE_URL}/control/v1/tenants`, async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'text/plain',
        body: 'backend unavailable'
      });
    });

    await page.goto('/ops/tenants');

    await expect(page.getByTestId('tenant-directory-error')).toBeVisible();
    await expect(page.getByText('Unable to load tenant directory.')).toBeVisible();
    await expect(page.getByText('Request failed (500): backend unavailable')).toBeVisible();
  });

  test('disables privileged actions when write scopes are missing', async ({ page }) => {
    await seedSession(page, ['control:tenants:read', 'control:config:read']);

    await page.route(`${CONTROL_API_BASE_URL}/control/v1/tenants`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            tenant_id: 'tenant-alpha',
            display_name: 'Alpha Bank',
            status: 'active',
            tier: 'enterprise',
            metadata_json: {},
            created_at: '2026-03-07T00:00:00Z',
            updated_at: '2026-03-07T00:00:00Z'
          }
        ])
      });
    });

    await page.route(`${CONTROL_API_BASE_URL}/control/v1/connectors/catalog`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            source_name: 'ofac_sls',
            source_type: 'sanctions',
            enabled: true,
            cadence_seconds: 3600,
            latest_status: 'ok',
            latest_run_at: '2026-03-07T00:00:00Z'
          }
        ])
      });
    });

    await page.goto('/ops/tenants');
    await expect(page.getByRole('button', { name: 'Create Tenant' })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Suspend' })).toBeDisabled();

    await page.getByRole('link', { name: 'Connectors' }).click();
    await expect(page.getByRole('button', { name: 'Run Now' })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Disable' })).toBeDisabled();
  });
});
