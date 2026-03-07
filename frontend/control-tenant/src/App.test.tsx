import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';

function createJwt(payload: Record<string, unknown>): string {
  const encoded = window
    .btoa(JSON.stringify(payload))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '');
  return `header.${encoded}.signature`;
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' }
  });
}

function textResponse(body: string, status = 200): Response {
  return new Response(body, {
    status,
    headers: { 'Content-Type': 'text/plain' }
  });
}

function findButtonByText(label: string): HTMLButtonElement {
  const button = Array.from(document.querySelectorAll('button')).find((item) => item.textContent?.trim() === label);
  if (!button) {
    throw new Error(`Unable to find button: ${label}`);
  }
  return button as HTMLButtonElement;
}

async function waitFor(assertion: () => void, timeoutMs = 2500) {
  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    try {
      assertion();
      return;
    } catch {
      await act(async () => {
        await new Promise((resolve) => window.setTimeout(resolve, 20));
      });
    }
  }

  assertion();
}

function expectText(text: string) {
  expect(document.body.textContent).toContain(text);
}

describe('tenant control console', () => {
  let root: Root | null = null;
  let queryClient: QueryClient | null = null;
  let fetchMock: ReturnType<typeof vi.fn>;
  let restoreMatchMedia: () => void = () => undefined;
  let restoreAnimationFrame: () => void = () => undefined;
  let restoreLocalStorage: () => void = () => undefined;

  async function renderApp(route: string) {
    const container = document.createElement('div');
    document.body.innerHTML = '';
    document.body.appendChild(container);
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          refetchOnWindowFocus: false
        }
      }
    });
    root = createRoot(container);

    await act(async () => {
      root?.render(
        <QueryClientProvider client={queryClient!}>
          <MemoryRouter initialEntries={[route]}>
            <App />
          </MemoryRouter>
        </QueryClientProvider>
      );
      await Promise.resolve();
    });
  }

  beforeEach(() => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

    const originalLocalStorage = window.localStorage;
    const storage = new Map<string, string>();
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => {
          storage.set(key, String(value));
        },
        removeItem: (key: string) => {
          storage.delete(key);
        },
        clear: () => {
          storage.clear();
        },
        key: (index: number) => Array.from(storage.keys())[index] ?? null,
        get length() {
          return storage.size;
        }
      }
    });
    restoreLocalStorage = () => {
      Object.defineProperty(window, 'localStorage', {
        configurable: true,
        value: originalLocalStorage
      });
    };

    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const matchMediaMock = vi.fn().mockImplementation(() => ({
      matches: false,
      media: '',
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn()
    }));
    const originalMatchMedia = window.matchMedia;
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      writable: true,
      value: matchMediaMock
    });
    restoreMatchMedia = () => {
      Object.defineProperty(window, 'matchMedia', {
        configurable: true,
        writable: true,
        value: originalMatchMedia
      });
    };

    const originalRaf = window.requestAnimationFrame;
    const originalCancelRaf = window.cancelAnimationFrame;
    window.requestAnimationFrame = ((callback: FrameRequestCallback) =>
      window.setTimeout(() => callback(performance.now()), 16)) as typeof window.requestAnimationFrame;
    window.cancelAnimationFrame = ((handle: number) => {
      window.clearTimeout(handle);
    }) as typeof window.cancelAnimationFrame;
    restoreAnimationFrame = () => {
      window.requestAnimationFrame = originalRaf;
      window.cancelAnimationFrame = originalCancelRaf;
    };
  });

  afterEach(async () => {
    if (root) {
      await act(async () => {
        root?.unmount();
      });
    }
    queryClient?.clear();
    root = null;
    queryClient = null;
    restoreMatchMedia();
    restoreAnimationFrame();
    restoreLocalStorage();
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = false;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    document.body.innerHTML = '';
  });

  it('shows the auth-required workspace shell when no session exists', async () => {
    fetchMock.mockResolvedValue(textResponse('missing', 401));

    await renderApp('/workspace/overview');

    await waitFor(() => {
      expectText('Authentication Required');
      expectText('Sign in through the monitoring app first.');
      expectText('Open Monitoring Login');
    });
  });

  it('renders the workspace overview with mocked control-api responses', async () => {
    window.localStorage.setItem(
      'risk_token',
      createJwt({
        sub: 'tenant@example.com',
        tenant_id: 'tenant-alpha',
        roles: ['admin'],
        scopes: ['control:config:read'],
        exp: Math.floor(Date.now() / 1000) + 3600
      })
    );
    window.localStorage.setItem('risk_username', 'tenant@example.com');

    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/control/v1/tenants/tenant-alpha/configuration')) {
        return jsonResponse({
          tenant_id: 'tenant-alpha',
          anomaly_threshold: 0.82,
          enabled_connectors: ['ofac_sls'],
          model_version: '20260301000000',
          rule_overrides_json: { high_amount_threshold: 10000 },
          version: 2,
          updated_at: '2026-03-07T00:00:00Z'
        });
      }
      if (url.endsWith('/control/v1/connectors/catalog')) {
        return jsonResponse([
          {
            source_name: 'ofac_sls',
            source_type: 'sanctions',
            enabled: true,
            cadence_seconds: 3600,
            latest_status: 'ok',
            latest_run_at: '2026-03-07T00:00:00Z'
          }
        ]);
      }
      if (url.endsWith('/control/v1/tenants/tenant-alpha/reconciliation/ingestion')) {
        return jsonResponse({
          tenant_id: 'tenant-alpha',
          from_ts: '2026-03-07T00:00:00Z',
          to_ts: '2026-03-07T01:00:00Z',
          ingested_events: 14,
          processed_decisions: 14,
          raised_alerts: 2,
          delivered_alerts: 2,
          failed_deliveries: 0,
          mismatch_count: 0
        });
      }
      throw new Error(`Unhandled request: ${url}`);
    });

    await renderApp('/workspace/overview');

    await waitFor(() => {
      expectText('Workspace Overview');
      expectText('Config version');
      expectText('Mismatch count');
      expectText('ofac_sls');
    });
  });

  it('saves connector policy changes with mocked control-api responses', async () => {
    window.localStorage.setItem(
      'risk_token',
      createJwt({
        sub: 'tenant@example.com',
        tenant_id: 'tenant-alpha',
        roles: ['admin'],
        scopes: ['control:config:read', 'control:config:write'],
        exp: Math.floor(Date.now() / 1000) + 3600
      })
    );
    window.localStorage.setItem('risk_username', 'tenant@example.com');

    const currentConfig = {
      tenant_id: 'tenant-alpha',
      anomaly_threshold: 0.82,
      enabled_connectors: ['ofac_sls'],
      model_version: null,
      rule_overrides_json: {},
      version: 2,
      updated_at: '2026-03-07T00:00:00Z'
    };
    let savedPayload: unknown = null;

    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/control/v1/tenants/tenant-alpha/configuration') && (init?.method ?? 'GET') === 'GET') {
        return jsonResponse(currentConfig);
      }
      if (url.endsWith('/control/v1/tenants/tenant-alpha/configuration') && init?.method === 'PUT') {
        savedPayload = JSON.parse(String(init.body));
        currentConfig.enabled_connectors = ['ofac_sls', 'fatf'];
        currentConfig.version = 3;
        return jsonResponse(currentConfig);
      }
      if (url.endsWith('/control/v1/connectors/catalog')) {
        return jsonResponse([
          {
            source_name: 'ofac_sls',
            source_type: 'sanctions',
            enabled: true,
            cadence_seconds: 3600,
            latest_status: 'ok',
            latest_run_at: '2026-03-07T00:00:00Z'
          },
          {
            source_name: 'fatf',
            source_type: 'watchlist',
            enabled: true,
            cadence_seconds: 7200,
            latest_status: 'ok',
            latest_run_at: '2026-03-07T00:00:00Z'
          }
        ]);
      }
      throw new Error(`Unhandled request: ${url}`);
    });

    await renderApp('/workspace/config/connectors');

    await waitFor(() => {
      expectText('Connector Policy');
      expectText('fatf');
    });

    const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]')) as HTMLInputElement[];
    expect(checkboxes).toHaveLength(2);

    await act(async () => {
      checkboxes[1].click();
    });

    await act(async () => {
      findButtonByText('Save Connector Policy').click();
    });

    await waitFor(() => {
      expect(savedPayload).toEqual({
        enabled_connectors: ['ofac_sls', 'fatf'],
        expected_version: 2
      });
      expectText('Connector policy saved for tenant-alpha.');
    });
  });
});
