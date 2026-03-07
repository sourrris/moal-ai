import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { Navigate, NavLink, Route, Routes } from 'react-router-dom';

import { ControlApiClient } from '../../packages/control-api-client/src/client';
import type {
  ConfigAuditItemDTO,
  ConnectorCatalogItem,
  DeliveryLogItemDTO,
  TenantSummary
} from '../../packages/control-api-client/src/types';
import { buildMonitoringLoginUrl } from '../../packages/control-auth/src/handoff';
import {
  DEFAULT_LIMIT,
  MAX_LIMIT,
  MIN_LIMIT,
  deriveSessionState,
  hasAllScopes,
  hasAnyScope,
  normalizeLimit,
  readHandedOffSession,
  type SessionState
} from './app-state';
import { getOpsPageMeta, OPS_HOME_PATH, OPS_PAGE_META } from './page-meta';
import {
  Badge,
  Button,
  ConsolePageFrame,
  ControlShell,
  DataPanel,
  DensityToggle,
  Input,
  QueryStatus,
  ScopeGate,
  Select,
  StatusBanner,
  buttonClassName,
  cn,
  useDensityPreference
} from './ui';

const CONTROL_API_BASE_URL = import.meta.env.VITE_CONTROL_API_BASE_URL ?? 'http://control-api.localhost';
const MONITORING_APP_URL = import.meta.env.VITE_MONITORING_APP_URL ?? 'http://app.localhost';
const MONITORING_API_BASE_URL = import.meta.env.VITE_MONITORING_API_BASE_URL ?? 'http://api.localhost';
const TENANT_CONSOLE_URL = import.meta.env.VITE_TENANT_CONSOLE_URL ?? 'http://control.localhost';

const OPS_SCOPE_RULES = {
  tenantsRead: ['control:tenants:read'],
  tenantsWrite: ['control:tenants:write'],
  configRead: ['control:config:read'],
  configWrite: ['control:config:write'],
  routingRead: ['control:routing:read'],
  auditReadAny: ['control:tenants:read', 'control:config:read']
} as const;

function getSessionState(): SessionState {
  const handedOffSession = readHandedOffSession();
  if (handedOffSession) {
    return handedOffSession;
  }
  const token = window.localStorage.getItem('risk_token');
  const username = window.localStorage.getItem('risk_username');
  return deriveSessionState(token, username);
}

type BootstrapSessionState = SessionState | { status: 'loading'; token: null; username: null; tenantId: 'all'; scopes: [] };

async function refreshMonitoringSession(): Promise<SessionState | null> {
  const response = await fetch(`${MONITORING_API_BASE_URL}/v1/auth/refresh`, {
    method: 'POST',
    credentials: 'include'
  });

  if (!response.ok) {
    return null;
  }

  const payload = (await response.json()) as { access_token?: string };
  if (!payload.access_token) {
    return null;
  }

  const username = window.localStorage.getItem('risk_username');
  const session = deriveSessionState(payload.access_token, username);
  if (session.status !== 'ready' || !session.token) {
    return null;
  }

  window.localStorage.setItem('risk_token', session.token);
  if (session.username) {
    window.localStorage.setItem('risk_username', session.username);
  }

  return session;
}

function useSessionBootstrap(): BootstrapSessionState {
  const [state, setState] = useState<BootstrapSessionState>(() => {
    const current = getSessionState();
    if (current.status === 'ready') {
      return current;
    }
    return { status: 'loading', token: null, username: null, tenantId: 'all', scopes: [] };
  });

  useEffect(() => {
    if (state.status !== 'loading') {
      return;
    }

    let cancelled = false;

    void refreshMonitoringSession()
      .then((session) => {
        if (cancelled) {
          return;
        }
        setState(session ?? getSessionState());
      })
      .catch(() => {
        if (!cancelled) {
          setState(getSessionState());
        }
      });

    return () => {
      cancelled = true;
    };
  }, [state.status]);

  return state;
}

function statusVariant(status: string | null | undefined) {
  if (status === 'active' || status === 'ok' || status === 'delivered') {
    return 'success' as const;
  }
  if (status === 'suspended' || status === 'failed') {
    return 'critical' as const;
  }
  if (status === 'pending' || status === 'partial') {
    return 'warning' as const;
  }
  return 'neutral' as const;
}

function navigationLinkClassName(isActive: boolean) {
  return cn('control-nav__link', isActive && 'control-nav__link--active');
}

function Navigation() {
  return (
    <nav className="control-nav" aria-label="Ops sections">
      {OPS_PAGE_META.map((item) => (
        <NavLink key={item.path} to={item.path} className={({ isActive }) => navigationLinkClassName(isActive)}>
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}

function EnvironmentChecklist() {
  const checks = [
    'Reverse proxy resolves ops-control.localhost, control.localhost, and control-api.localhost.',
    'The ops console frontend responds at http://ops-control.localhost.',
    'The control API responds at http://control-api.localhost/health/live.',
    'Browser storage contains a valid risk_token and optional risk_username for authenticated flows.'
  ];

  return (
    <DataPanel title="Playwright Preflight" description="Quick checks for local operator and browser automation flows.">
      <ul className="control-list" data-testid="preflight-checklist">
        {checks.map((check) => (
          <li key={check} className="control-list__item">
            <span>{check}</span>
          </li>
        ))}
      </ul>
    </DataPanel>
  );
}

function AuthRequiredPanel({ invalidSession }: { invalidSession: boolean }) {
  return (
    <DataPanel title="Authentication Required" description="This console reuses the shared monitoring session.">
      <p data-testid="auth-required-message" className="muted">
        {invalidSession
          ? 'The saved session is invalid or expired. Sign in again through the monitoring app.'
          : 'Sign in through the monitoring app first. This console reuses the same JWT session.'}
      </p>
      <div className="control-responsive-actions">
        <a className={buttonClassName('primary')} href={buildMonitoringLoginUrl(MONITORING_APP_URL, window.location.href)}>
          Open Monitoring Login
        </a>
        <a className={buttonClassName('secondary')} href={TENANT_CONSOLE_URL}>
          Open Tenant Console
        </a>
      </div>
    </DataPanel>
  );
}

function SessionCapabilities({ scopes }: { scopes: string[] }) {
  return (
    <DataPanel
      title="Session Capabilities"
      description="Current token scopes available to this operator session."
      badge={<Badge variant={scopes.length > 0 ? 'success' : 'warning'}>{scopes.length} scopes</Badge>}
    >
      {scopes.length > 0 ? (
        <div className="control-chip-row">
          {scopes.map((scope) => (
            <Badge key={scope} variant="info">
              {scope}
            </Badge>
          ))}
        </div>
      ) : (
        <p className="muted">No scopes found.</p>
      )}
    </DataPanel>
  );
}

function TenantsTable({
  tenants,
  onToggleStatus,
  togglePending,
  allowWrite
}: {
  tenants: TenantSummary[];
  onToggleStatus: (tenant: TenantSummary) => void;
  togglePending: boolean;
  allowWrite: boolean;
}) {
  return (
    <div className="control-table-wrap">
      <table className="control-table">
        <thead>
          <tr>
            <th scope="col">Tenant</th>
            <th scope="col">Display Name</th>
            <th scope="col">Tier</th>
            <th scope="col">Status</th>
            <th scope="col">Actions</th>
          </tr>
        </thead>
        <tbody>
          {tenants.map((tenant) => (
            <tr key={tenant.tenant_id}>
              <td className="mono">{tenant.tenant_id}</td>
              <td>{tenant.display_name}</td>
              <td>
                <Badge variant="neutral">{tenant.tier}</Badge>
              </td>
              <td>
                <Badge variant={statusVariant(tenant.status)}>{tenant.status}</Badge>
              </td>
              <td>
                <div className="control-inline-actions">
                  <Button
                    onClick={() => onToggleStatus(tenant)}
                    disabled={!allowWrite || togglePending}
                    title={allowWrite ? undefined : 'Requires control:tenants:write'}
                  >
                    {tenant.status === 'active' ? 'Suspend' : 'Activate'}
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TenantsPage({ client, scopes }: { client: ControlApiClient; scopes: string[] }) {
  const queryClient = useQueryClient();
  const canRead = hasAllScopes(scopes, [...OPS_SCOPE_RULES.tenantsRead]);
  const canWrite = hasAllScopes(scopes, [...OPS_SCOPE_RULES.tenantsWrite]);
  const tenantsQuery = useQuery({
    queryKey: ['ops-tenants'],
    queryFn: () => client.listTenants(),
    enabled: canRead
  });

  const [tenantId, setTenantId] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [tier, setTier] = useState('standard');
  const [status, setStatus] = useState('active');
  const [adminTenant, setAdminTenant] = useState('');
  const [adminUsername, setAdminUsername] = useState('');
  const [adminRole, setAdminRole] = useState('admin');

  const createMutation = useMutation({
    mutationFn: () =>
      client.createTenant({
        tenant_id: tenantId.trim(),
        display_name: displayName.trim(),
        tier: tier.trim(),
        status
      }),
    onSuccess: () => {
      setTenantId('');
      setDisplayName('');
      setTier('standard');
      setStatus('active');
      queryClient.invalidateQueries({ queryKey: ['ops-tenants'] });
    }
  });

  const updateMutation = useMutation({
    mutationFn: ({ tenant, nextStatus }: { tenant: TenantSummary; nextStatus: 'active' | 'suspended' }) =>
      client.updateTenant(tenant.tenant_id, { status: nextStatus }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ops-tenants'] });
    }
  });

  const assignMutation = useMutation({
    mutationFn: () =>
      client.assignTenantAdmin(adminTenant.trim(), {
        username: adminUsername.trim(),
        role_name: adminRole.trim()
      }),
    onSuccess: () => {
      setAdminTenant('');
      setAdminUsername('');
      setAdminRole('admin');
    }
  });

  const meta = getOpsPageMeta('/ops/tenants');

  return (
    <ConsolePageFrame
      title={meta.title}
      subtitle={meta.subtitle}
      chips={<Badge variant={canWrite ? 'success' : 'warning'}>{canWrite ? 'write enabled' : 'read only'}</Badge>}
    >
      <ScopeGate
        allowed={canRead}
        title="Tenant Operations Restricted"
        message="This session is missing control:tenants:read, so tenant data cannot be shown."
      >
        <div className="control-grid-two">
          <DataPanel title="Tenant Lifecycle" description="Create or suspend tenant workspaces from the control plane.">
            <div className="control-field-grid control-field-grid--four">
              <div className="control-field">
                <label htmlFor="tenant-id">Tenant ID</label>
                <Input id="tenant-id" value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="tenant-gamma" />
              </div>
              <div className="control-field">
                <label htmlFor="tenant-name">Display name</label>
                <Input
                  id="tenant-name"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  placeholder="Gamma Bank"
                />
              </div>
              <div className="control-field">
                <label htmlFor="tenant-tier">Tier</label>
                <Input id="tenant-tier" value={tier} onChange={(event) => setTier(event.target.value)} placeholder="enterprise" />
              </div>
              <div className="control-field">
                <label htmlFor="tenant-status">Status</label>
                <Select id="tenant-status" value={status} onChange={(event) => setStatus(event.target.value)}>
                  <option value="active">active</option>
                  <option value="suspended">suspended</option>
                </Select>
              </div>
            </div>

            <div className="control-responsive-actions">
              <Button
                variant="primary"
                onClick={() => createMutation.mutate()}
                disabled={createMutation.isPending || !canWrite || !tenantId.trim() || !displayName.trim() || !tier.trim()}
                title={canWrite ? undefined : 'Requires control:tenants:write'}
              >
                {createMutation.isPending ? 'Creating...' : 'Create Tenant'}
              </Button>
            </div>

            {createMutation.isError ? (
              <StatusBanner variant="error">{(createMutation.error as Error).message}</StatusBanner>
            ) : null}
          </DataPanel>

          <DataPanel title="Assign Tenant Admin" description="Delegate an initial administrator to a tenant workspace.">
            <div className="control-field-grid control-field-grid--three">
              <div className="control-field">
                <label htmlFor="admin-tenant">Tenant</label>
                <Input
                  id="admin-tenant"
                  value={adminTenant}
                  onChange={(event) => setAdminTenant(event.target.value)}
                  placeholder="tenant-gamma"
                />
              </div>
              <div className="control-field">
                <label htmlFor="admin-username">Username</label>
                <Input
                  id="admin-username"
                  value={adminUsername}
                  onChange={(event) => setAdminUsername(event.target.value)}
                  placeholder="user@example.com"
                />
              </div>
              <div className="control-field">
                <label htmlFor="admin-role">Role</label>
                <Input
                  id="admin-role"
                  value={adminRole}
                  onChange={(event) => setAdminRole(event.target.value)}
                  placeholder="admin"
                />
              </div>
            </div>

            <div className="control-responsive-actions">
              <Button
                variant="secondary"
                onClick={() => assignMutation.mutate()}
                disabled={assignMutation.isPending || !canWrite || !adminTenant.trim() || !adminUsername.trim() || !adminRole.trim()}
                title={canWrite ? undefined : 'Requires control:tenants:write'}
              >
                {assignMutation.isPending ? 'Assigning...' : 'Assign Admin'}
              </Button>
            </div>

            {assignMutation.isError ? (
              <StatusBanner variant="error">{(assignMutation.error as Error).message}</StatusBanner>
            ) : null}
          </DataPanel>
        </div>

        <DataPanel title="Tenant Directory" description="Current tenants and lifecycle status across the control plane.">
          {tenantsQuery.isPending ? <QueryStatus state="loading" subject="tenant directory" /> : null}
          {tenantsQuery.isError ? (
            <QueryStatus state="error" subject="tenant directory" error={(tenantsQuery.error as Error).message} />
          ) : null}
          {tenantsQuery.data && tenantsQuery.data.length === 0 ? <QueryStatus state="empty" subject="tenant directory" /> : null}
          {tenantsQuery.data && tenantsQuery.data.length > 0 ? (
            <TenantsTable
              tenants={tenantsQuery.data}
              onToggleStatus={(tenant) =>
                updateMutation.mutate({
                  tenant,
                  nextStatus: tenant.status === 'active' ? 'suspended' : 'active'
                })
              }
              togglePending={updateMutation.isPending}
              allowWrite={canWrite}
            />
          ) : null}
          {updateMutation.isError ? <StatusBanner variant="error">{(updateMutation.error as Error).message}</StatusBanner> : null}
        </DataPanel>
      </ScopeGate>
    </ConsolePageFrame>
  );
}

function ConnectorsTable({
  connectors,
  canWrite,
  runPending,
  togglePending,
  onRunNow,
  onToggle
}: {
  connectors: ConnectorCatalogItem[];
  canWrite: boolean;
  runPending: boolean;
  togglePending: boolean;
  onRunNow: (sourceName: string) => void;
  onToggle: (sourceName: string, enabled: boolean) => void;
}) {
  return (
    <div className="control-table-wrap">
      <table className="control-table">
        <thead>
          <tr>
            <th scope="col">Source</th>
            <th scope="col">Type</th>
            <th scope="col">Enabled</th>
            <th scope="col">Last Status</th>
            <th scope="col">Actions</th>
          </tr>
        </thead>
        <tbody>
          {connectors.map((connector) => (
            <tr key={connector.source_name}>
              <td className="mono">{connector.source_name}</td>
              <td>{connector.source_type}</td>
              <td>
                <Badge variant={connector.enabled ? 'success' : 'warning'}>{connector.enabled ? 'yes' : 'no'}</Badge>
              </td>
              <td>
                <Badge variant={statusVariant(connector.latest_status)}>{connector.latest_status ?? 'n/a'}</Badge>
              </td>
              <td>
                <div className="control-inline-actions">
                  <Button
                    onClick={() => onRunNow(connector.source_name)}
                    disabled={!canWrite || runPending}
                    title={canWrite ? undefined : 'Requires control:config:write'}
                  >
                    Run Now
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => onToggle(connector.source_name, !connector.enabled)}
                    disabled={!canWrite || togglePending}
                    title={canWrite ? undefined : 'Requires control:config:write'}
                  >
                    {connector.enabled ? 'Disable' : 'Enable'}
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ConnectorsPage({ client, scopes }: { client: ControlApiClient; scopes: string[] }) {
  const queryClient = useQueryClient();
  const canRead = hasAllScopes(scopes, [...OPS_SCOPE_RULES.configRead]);
  const canWrite = hasAllScopes(scopes, [...OPS_SCOPE_RULES.configWrite]);
  const catalogQuery = useQuery({
    queryKey: ['ops-connector-catalog'],
    queryFn: () => client.listConnectorsCatalog(),
    enabled: canRead
  });
  const [lastAction, setLastAction] = useState('');

  const runNowMutation = useMutation({
    mutationFn: (sourceName: string) => client.runConnectorNow(sourceName),
    onSuccess: (data) => {
      setLastAction(`Run-now dispatched for ${data.source_name}`);
      queryClient.invalidateQueries({ queryKey: ['ops-connector-catalog'] });
    }
  });

  const toggleMutation = useMutation({
    mutationFn: ({ sourceName, enabled }: { sourceName: string; enabled: boolean }) =>
      enabled ? client.globalEnableConnector(sourceName) : client.globalDisableConnector(sourceName),
    onSuccess: (data) => {
      setLastAction(`${data.source_name} is now ${data.enabled ? 'enabled' : 'disabled'}`);
      queryClient.invalidateQueries({ queryKey: ['ops-connector-catalog'] });
    }
  });

  const meta = getOpsPageMeta('/ops/connectors');

  return (
    <ConsolePageFrame
      title={meta.title}
      subtitle={meta.subtitle}
      chips={<Badge variant={canWrite ? 'success' : 'warning'}>{canWrite ? 'write enabled' : 'read only'}</Badge>}
    >
      <ScopeGate
        allowed={canRead}
        title="Connector Operations Restricted"
        message="This session is missing control:config:read, so connector status cannot be shown."
      >
        <DataPanel
          title="Global Connector Operations"
          description="Manage global feed availability and dispatch run-now actions without leaving the console."
        >
          {lastAction ? (
            <StatusBanner variant="success" data-testid="connector-last-action">
              {lastAction}
            </StatusBanner>
          ) : null}
          {catalogQuery.isPending ? <QueryStatus state="loading" subject="connector catalog" /> : null}
          {catalogQuery.isError ? (
            <QueryStatus state="error" subject="connector catalog" error={(catalogQuery.error as Error).message} />
          ) : null}
          {catalogQuery.data && catalogQuery.data.length === 0 ? <QueryStatus state="empty" subject="connector catalog" /> : null}
          {catalogQuery.data && catalogQuery.data.length > 0 ? (
            <ConnectorsTable
              connectors={catalogQuery.data}
              canWrite={canWrite}
              runPending={runNowMutation.isPending}
              togglePending={toggleMutation.isPending}
              onRunNow={(sourceName) => runNowMutation.mutate(sourceName)}
              onToggle={(sourceName, enabled) => toggleMutation.mutate({ sourceName, enabled })}
            />
          ) : null}
          {runNowMutation.isError || toggleMutation.isError ? (
            <StatusBanner variant="error">{((runNowMutation.error ?? toggleMutation.error) as Error).message}</StatusBanner>
          ) : null}
        </DataPanel>
      </ScopeGate>
    </ConsolePageFrame>
  );
}

function DeliveryTable({ rows }: { rows: DeliveryLogItemDTO[] }) {
  return (
    <div className="control-table-wrap">
      <table className="control-table">
        <thead>
          <tr>
            <th scope="col">Tenant</th>
            <th scope="col">Channel</th>
            <th scope="col">Status</th>
            <th scope="col">Attempt</th>
            <th scope="col">Time</th>
            <th scope="col">Error</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.delivery_id}>
              <td className="mono">{row.tenant_id}</td>
              <td>{row.channel}</td>
              <td>
                <Badge variant={statusVariant(row.status)}>{row.status}</Badge>
              </td>
              <td>{row.attempt_no}</td>
              <td>{new Date(row.attempted_at).toLocaleString()}</td>
              <td>{row.error_message ?? '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DeliveryPage({ client, scopes }: { client: ControlApiClient; scopes: string[] }) {
  const canRead = hasAllScopes(scopes, [...OPS_SCOPE_RULES.routingRead]);
  const [tenantFilter, setTenantFilter] = useState('');
  const [limitInput, setLimitInput] = useState(String(DEFAULT_LIMIT));
  const limit = normalizeLimit(limitInput);

  const deliveryQuery = useQuery({
    queryKey: ['ops-delivery', tenantFilter, limit],
    queryFn: () =>
      client.listDeliveryLogs({
        tenant_id: tenantFilter.trim() || undefined,
        limit
      }),
    enabled: canRead
  });

  const meta = getOpsPageMeta('/ops/delivery');

  return (
    <ConsolePageFrame
      title={meta.title}
      subtitle={meta.subtitle}
      chips={<Badge variant={canRead ? 'info' : 'warning'}>{canRead ? 'routing read' : 'restricted'}</Badge>}
    >
      <ScopeGate
        allowed={canRead}
        title="Delivery Logs Restricted"
        message="This session is missing control:routing:read, so delivery logs cannot be shown."
      >
        <DataPanel title="Cross-Tenant Delivery Logs" description="Filter recent alert deliveries across tenant destinations.">
          <div className="control-field-grid">
            <div className="control-field">
              <label htmlFor="delivery-tenant-filter">Tenant filter</label>
              <Input
                id="delivery-tenant-filter"
                value={tenantFilter}
                onChange={(event) => setTenantFilter(event.target.value)}
                placeholder="tenant filter (optional)"
              />
            </div>
            <div className="control-field">
              <label htmlFor="delivery-limit">Limit</label>
              <Input
                id="delivery-limit"
                value={limitInput}
                type="number"
                min={MIN_LIMIT}
                max={MAX_LIMIT}
                onChange={(event) => setLimitInput(event.target.value)}
              />
            </div>
          </div>

          <p className="muted" data-testid="delivery-limit-summary">
            Requesting up to {limit} delivery records per fetch.
          </p>

          {deliveryQuery.isPending ? <QueryStatus state="loading" subject="delivery logs" /> : null}
          {deliveryQuery.isError ? (
            <QueryStatus state="error" subject="delivery logs" error={(deliveryQuery.error as Error).message} />
          ) : null}
          {deliveryQuery.data && deliveryQuery.data.length === 0 ? <QueryStatus state="empty" subject="delivery logs" /> : null}
          {deliveryQuery.data && deliveryQuery.data.length > 0 ? <DeliveryTable rows={deliveryQuery.data} /> : null}
        </DataPanel>
      </ScopeGate>
    </ConsolePageFrame>
  );
}

function AuditTable({ rows }: { rows: ConfigAuditItemDTO[] }) {
  return (
    <div className="control-table-wrap">
      <table className="control-table">
        <thead>
          <tr>
            <th scope="col">When</th>
            <th scope="col">Actor</th>
            <th scope="col">Tenant</th>
            <th scope="col">Action</th>
            <th scope="col">Resource</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{new Date(row.created_at).toLocaleString()}</td>
              <td>{row.actor}</td>
              <td>{row.tenant_id ?? 'global'}</td>
              <td>{row.action}</td>
              <td>{row.resource_type}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AuditPage({ client, scopes }: { client: ControlApiClient; scopes: string[] }) {
  const canRead = hasAnyScope(scopes, [...OPS_SCOPE_RULES.auditReadAny]);
  const [tenantFilter, setTenantFilter] = useState('');
  const [limitInput, setLimitInput] = useState(String(DEFAULT_LIMIT));
  const limit = normalizeLimit(limitInput);

  const auditQuery = useQuery({
    queryKey: ['ops-audit', tenantFilter, limit],
    queryFn: () =>
      client.listAuditConfigChanges({
        tenant_id: tenantFilter.trim() || undefined,
        limit
      }),
    enabled: canRead
  });

  const meta = getOpsPageMeta('/ops/audit');

  return (
    <ConsolePageFrame
      title={meta.title}
      subtitle={meta.subtitle}
      chips={<Badge variant={canRead ? 'info' : 'warning'}>{canRead ? 'audit enabled' : 'restricted'}</Badge>}
    >
      <ScopeGate
        allowed={canRead}
        title="Audit Trail Restricted"
        message="This session is missing control:tenants:read or control:config:read, so config audit history cannot be shown."
      >
        <DataPanel title="Configuration Audit Trail" description="Search and inspect recent control-plane config mutations.">
          <div className="control-field-grid">
            <div className="control-field">
              <label htmlFor="audit-tenant-filter">Tenant filter</label>
              <Input
                id="audit-tenant-filter"
                value={tenantFilter}
                onChange={(event) => setTenantFilter(event.target.value)}
                placeholder="tenant filter (optional)"
              />
            </div>
            <div className="control-field">
              <label htmlFor="audit-limit">Limit</label>
              <Input
                id="audit-limit"
                value={limitInput}
                type="number"
                min={MIN_LIMIT}
                max={MAX_LIMIT}
                onChange={(event) => setLimitInput(event.target.value)}
              />
            </div>
          </div>

          <p className="muted" data-testid="audit-limit-summary">
            Requesting up to {limit} audit records per fetch.
          </p>

          {auditQuery.isPending ? <QueryStatus state="loading" subject="audit trail" /> : null}
          {auditQuery.isError ? (
            <QueryStatus state="error" subject="audit trail" error={(auditQuery.error as Error).message} />
          ) : null}
          {auditQuery.data && auditQuery.data.length === 0 ? <QueryStatus state="empty" subject="audit trail" /> : null}
          {auditQuery.data && auditQuery.data.length > 0 ? <AuditTable rows={auditQuery.data} /> : null}
        </DataPanel>
      </ScopeGate>
    </ConsolePageFrame>
  );
}

export function App() {
  const { status, token, username, tenantId, scopes } = useSessionBootstrap();
  const [density, setDensity] = useDensityPreference('control_ops_density');

  const client = useMemo(() => {
    if (!token) {
      return null;
    }
    return new ControlApiClient(CONTROL_API_BASE_URL, token);
  }, [token]);

  const brand = (
    <NavLink to={OPS_HOME_PATH} className="control-brand">
      <span className="control-brand__mark">ops</span>
      <span className="control-brand__copy">
        <span className="control-brand__eyebrow">Control Plane</span>
        <span className="control-brand__name">Aegis Operations Console</span>
      </span>
    </NavLink>
  );

  if (status === 'loading') {
    return (
      <ControlShell brand={brand}>
        <EnvironmentChecklist />
        <DataPanel title="Checking Monitoring Session" description="Verifying the shared monitoring sign-in before opening the ops console.">
          <p className="muted">Verifying the shared monitoring sign-in before opening the ops console.</p>
        </DataPanel>
      </ControlShell>
    );
  }

  if (!client || status !== 'ready') {
    return (
      <ControlShell brand={brand}>
        <EnvironmentChecklist />
        <AuthRequiredPanel invalidSession={status === 'invalid'} />
      </ControlShell>
    );
  }

  return (
    <ControlShell
      brand={brand}
      navigation={<Navigation />}
      actions={
        <>
          <span className="control-inline-meta">
            {username ?? 'operator'} · {tenantId}
          </span>
          <a className={buttonClassName('ghost')} href={TENANT_CONSOLE_URL}>
            Open Tenant Console
          </a>
          <a className={buttonClassName('ghost')} href={MONITORING_APP_URL}>
            Open Monitoring App
          </a>
        </>
      }
      utilityBar={
        <div className="control-responsive-actions">
          <Badge variant="success">session ready</Badge>
          <Badge variant="info">{tenantId}</Badge>
          <Badge variant={scopes.length > 0 ? 'success' : 'warning'}>{scopes.length} scopes</Badge>
          <DensityToggle value={density} onChange={setDensity} />
        </div>
      }
    >
      <SessionCapabilities scopes={scopes} />
      <Routes>
        <Route path="/" element={<Navigate to={OPS_HOME_PATH} replace />} />
        <Route path="/ops/tenants" element={<TenantsPage client={client} scopes={scopes} />} />
        <Route path="/ops/connectors" element={<ConnectorsPage client={client} scopes={scopes} />} />
        <Route path="/ops/delivery" element={<DeliveryPage client={client} scopes={scopes} />} />
        <Route path="/ops/audit" element={<AuditPage client={client} scopes={scopes} />} />
        <Route path="*" element={<Navigate to={OPS_HOME_PATH} replace />} />
      </Routes>
    </ControlShell>
  );
}
