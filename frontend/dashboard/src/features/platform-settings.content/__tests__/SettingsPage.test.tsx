import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

const mockFetchDomains = vi.fn();
const mockFetchApiKeys = vi.fn();
const mockToast = vi.fn();

vi.mock('../../../app/state/auth-context', () => ({
  useAuth: () => ({ token: 'test-token', username: 'admin', tenantId: 'tenant-gamma' })
}));

vi.mock('../../../app/state/ui-context', () => ({
  useUI: () => ({
    theme: 'light',
    setTheme: vi.fn(),
    timezone: 'local',
    setTimezone: vi.fn(),
    tenant: 'tenant-gamma',
    window: '24h',
    density: 'compact'
  })
}));

vi.mock('../../../shared/api/setup', () => ({
  fetchDomains: (...args: unknown[]) => mockFetchDomains(...args),
  fetchApiKeys: (...args: unknown[]) => mockFetchApiKeys(...args),
  createDomain: vi.fn(),
  createApiKey: vi.fn(),
  revokeApiKey: vi.fn()
}));

vi.mock('../../../shared/ui/toaster', () => ({
  useToast: () => ({ toast: mockToast })
}));

import { SettingsPage } from '../SettingsPage';

const routerFuture = {
  v7_startTransition: true,
  v7_relativeSplatPath: true,
} as const;

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={routerFuture} initialEntries={['/settings']}>
        <SettingsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('SettingsPage', () => {
  it('renders control console links and setup inventory panels', async () => {
    mockFetchDomains.mockResolvedValue({
      items: [
        {
          domain_id: 'domain-1',
          tenant_id: 'tenant-gamma',
          hostname: 'app.example.com',
          created_at: '2026-03-08T12:00:00Z'
        }
      ]
    });
    mockFetchApiKeys.mockResolvedValue({
      items: [
        {
          key_id: 'key-1',
          tenant_id: 'tenant-gamma',
          name: 'Web ingest key',
          key_prefix: 'test-key-prefix',
          active: true,
          scopes: ['events:write'],
          domain_id: 'domain-1',
          domain_hostname: 'app.example.com',
          created_at: '2026-03-08T12:00:00Z',
          last_used_at: null
        }
      ]
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Registered domains')).toBeInTheDocument();
      expect(screen.getByText('API keys')).toBeInTheDocument();
      expect(screen.getAllByText('app.example.com').length).toBeGreaterThan(0);
      expect(screen.getByText('Web ingest key')).toBeInTheDocument();
    });

    const tenantLink = screen.getByRole('link', { name: 'Open Tenant Control Console' });
    const opsLink = screen.getByRole('link', { name: 'Open Ops Control Console' });

    expect(tenantLink.getAttribute('href')).toContain('http://control.localhost/#aegis-handoff:');
    expect(opsLink.getAttribute('href')).toContain('http://ops-control.localhost/#aegis-handoff:');
    expect(tenantLink.getAttribute('href')).toContain('token=test-token');
    expect(tenantLink.getAttribute('href')).toContain('username=admin');
    expect(opsLink.getAttribute('href')).toContain('token=test-token');
    expect(opsLink.getAttribute('href')).toContain('username=admin');
  });
});
