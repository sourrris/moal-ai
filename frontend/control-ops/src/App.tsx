import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { Navigate, NavLink, Route, Routes } from 'react-router-dom';

import { ControlApiClient } from '../../packages/control-api-client/src/client';
import type { ConfigAuditItemDTO, ConnectorCatalogItem, DeliveryLogItemDTO, TenantSummary } from '../../packages/control-api-client/src/types';
import {
  DEFAULT_LIMIT,
  MAX_LIMIT,
  MIN_LIMIT,
  deriveSessionState,
  hasAllScopes,
  hasAnyScope,
  normalizeLimit,
  type SessionState
} from './app-state';
import { Badge, OpsShell, Panel } from './ui';

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
  if (session.status !== 'ready') {
    return null;
  }

  const token = session.token;
  if (!token) {
    return null;
  }

  window.localStorage.setItem('risk_token', token);
  if (session.username) {
    window.localStorage.setItem('risk_username', session.username);
  }

  return { ...session, token };
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

function Navigation() {
  return (
    <nav aria-label="Ops sections" style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
      <NavLink to="/ops/tenants">Tenants</NavLink>
      <NavLink to="/ops/connectors">Connectors</NavLink>
      <NavLink to="/ops/delivery">Delivery</NavLink>
      <NavLink to="/ops/audit">Audit</NavLink>
    </nav>
  );
}

function QueryStatus({
  state,
  subject,
  error
}: {
  state: 'loading' | 'error' | 'empty';
  subject: string;
  error?: string;
}) {
  const message =
    state === 'loading'
      ? `Loading ${subject}.`
      : state === 'empty'
        ? `No ${subject} available yet.`
        : `Unable to load ${subject}.`;

  return (
    <div aria-live="polite" data-testid={`${subject.replace(/\s+/g, '-').toLowerCase()}-${state}`}>
      <p>{message}</p>
      {state === 'error' && error ? <p style={{ color: '#b91c1c' }}>{error}</p> : null}
    </div>
  );
}

function ScopeGate({
  allowed,
  title,
  message,
  children
}: {
  allowed: boolean;
  title: string;
  message: string;
  children: JSX.Element;
}) {
  if (allowed) {
    return children;
  }

  return (
    <Panel title={title}>
      <p data-testid="scope-gate-message">{message}</p>
    </Panel>
  );
}

function EnvironmentChecklist() {
  const checks = [
    'Reverse proxy is running and resolves ops-control.localhost, control.localhost, and control-api.localhost.',
    'The ops console frontend responds at http://ops-control.localhost.',
    'The control API responds at http://control-api.localhost/health/live.',
    'Browser storage contains a valid risk_token and optional risk_username for authenticated flows.'
  ];

  return (
    <Panel title="Playwright Preflight">
      <ul data-testid="preflight-checklist" style={{ margin: 0, paddingLeft: 18 }}>
        {checks.map((check) => (
          <li key={check}>{check}</li>
        ))}
      </ul>
    </Panel>
  );
}

function AuthRequiredPanel({ invalidSession }: { invalidSession: boolean }) {
  return (
    <Panel title="Authentication Required">
      <p data-testid="auth-required-message">
        {invalidSession
          ? 'The saved session is invalid or expired. Sign in again through the monitoring app.'
          : 'Sign in through the monitoring app first. This console reuses the same JWT session.'}
      </p>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <a href={`${MONITORING_APP_URL}/login`}>Open Monitoring Login</a>
        <a href={TENANT_CONSOLE_URL}>Open Tenant Console</a>
      </div>
    </Panel>
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
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr>
          <th align="left">Tenant</th>
          <th align="left">Display Name</th>
          <th align="left">Tier</th>
          <th align="left">Status</th>
          <th align="left">Actions</th>
        </tr>
      </thead>
      <tbody>
        {tenants.map((tenant) => (
          <tr key={tenant.tenant_id} style={{ borderTop: '1px solid #e2e8f0' }}>
            <td>{tenant.tenant_id}</td>
            <td>{tenant.display_name}</td>
            <td>{tenant.tier}</td>
            <td>
              {tenant.status}
              <Badge value={tenant.status === 'active' ? 'healthy' : 'attention'} />
            </td>
            <td>
              <button
                onClick={() => onToggleStatus(tenant)}
                disabled={!allowWrite || togglePending}
                title={allowWrite ? undefined : 'Requires control:tenants:write'}
              >
                {tenant.status === 'active' ? 'Suspend' : 'Activate'}
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
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
    }
  });

  return (
    <ScopeGate
      allowed={canRead}
      title="Tenant Operations Restricted"
      message="This session is missing control:tenants:read, so tenant data cannot be shown."
    >
      <>
        <Panel title="Tenant Lifecycle">
          <p>Create or suspend tenants from the control plane without direct DB access.</p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(150px, 1fr))', gap: 10 }}>
            <input value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="tenant-gamma" />
            <input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="Gamma Bank"
            />
            <input value={tier} onChange={(event) => setTier(event.target.value)} placeholder="enterprise" />
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="active">active</option>
              <option value="suspended">suspended</option>
            </select>
          </div>
          <button
            style={{ marginTop: 10 }}
            onClick={() => createMutation.mutate()}
            disabled={createMutation.isPending || !canWrite || !tenantId.trim() || !displayName.trim() || !tier.trim()}
            title={canWrite ? undefined : 'Requires control:tenants:write'}
          >
            {createMutation.isPending ? 'Creating...' : 'Create Tenant'}
          </button>
          {createMutation.isError ? <p style={{ color: '#b91c1c' }}>{(createMutation.error as Error).message}</p> : null}
        </Panel>

        <Panel title="Assign Tenant Admin">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(180px, 1fr))', gap: 10 }}>
            <input
              value={adminTenant}
              onChange={(event) => setAdminTenant(event.target.value)}
              placeholder="tenant-gamma"
            />
            <input
              value={adminUsername}
              onChange={(event) => setAdminUsername(event.target.value)}
              placeholder="user@example.com"
            />
            <input value={adminRole} onChange={(event) => setAdminRole(event.target.value)} placeholder="admin" />
          </div>
          <button
            style={{ marginTop: 10 }}
            onClick={() => assignMutation.mutate()}
            disabled={assignMutation.isPending || !canWrite || !adminTenant.trim() || !adminUsername.trim() || !adminRole.trim()}
            title={canWrite ? undefined : 'Requires control:tenants:write'}
          >
            {assignMutation.isPending ? 'Assigning...' : 'Assign Admin'}
          </button>
          {assignMutation.isError ? <p style={{ color: '#b91c1c' }}>{(assignMutation.error as Error).message}</p> : null}
        </Panel>

        <Panel title="Tenant Directory">
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
          {updateMutation.isError ? <p style={{ color: '#b91c1c' }}>{(updateMutation.error as Error).message}</p> : null}
        </Panel>
      </>
    </ScopeGate>
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
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr>
          <th align="left">Source</th>
          <th align="left">Type</th>
          <th align="left">Enabled</th>
          <th align="left">Last Status</th>
          <th align="left">Actions</th>
        </tr>
      </thead>
      <tbody>
        {connectors.map((connector) => (
          <tr key={connector.source_name} style={{ borderTop: '1px solid #e2e8f0' }}>
            <td>{connector.source_name}</td>
            <td>{connector.source_type}</td>
            <td>{connector.enabled ? 'yes' : 'no'}</td>
            <td>{connector.latest_status ?? 'n/a'}</td>
            <td style={{ display: 'flex', gap: 8, padding: '10px 0' }}>
              <button
                onClick={() => onRunNow(connector.source_name)}
                disabled={!canWrite || runPending}
                title={canWrite ? undefined : 'Requires control:config:write'}
              >
                Run Now
              </button>
              <button
                onClick={() => onToggle(connector.source_name, !connector.enabled)}
                disabled={!canWrite || togglePending}
                title={canWrite ? undefined : 'Requires control:config:write'}
              >
                {connector.enabled ? 'Disable' : 'Enable'}
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
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

  return (
    <ScopeGate
      allowed={canRead}
      title="Connector Operations Restricted"
      message="This session is missing control:config:read, so connector status cannot be shown."
    >
      <Panel title="Global Connector Operations">
        {lastAction ? <p data-testid="connector-last-action">{lastAction}</p> : null}
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
          <p style={{ color: '#b91c1c' }}>
            {((runNowMutation.error ?? toggleMutation.error) as Error).message}
          </p>
        ) : null}
      </Panel>
    </ScopeGate>
  );
}

function DeliveryTable({ rows }: { rows: DeliveryLogItemDTO[] }) {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr>
          <th align="left">Tenant</th>
          <th align="left">Channel</th>
          <th align="left">Status</th>
          <th align="left">Attempt</th>
          <th align="left">Time</th>
          <th align="left">Error</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.delivery_id} style={{ borderTop: '1px solid #e2e8f0' }}>
            <td>{row.tenant_id}</td>
            <td>{row.channel}</td>
            <td>{row.status}</td>
            <td>{row.attempt_no}</td>
            <td>{new Date(row.attempted_at).toLocaleString()}</td>
            <td>{row.error_message ?? '-'}</td>
          </tr>
        ))}
      </tbody>
    </table>
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

  return (
    <ScopeGate
      allowed={canRead}
      title="Delivery Logs Restricted"
      message="This session is missing control:routing:read, so delivery logs cannot be shown."
    >
      <Panel title="Cross-Tenant Delivery Logs">
        <div style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
          <input
            value={tenantFilter}
            onChange={(event) => setTenantFilter(event.target.value)}
            placeholder="tenant filter (optional)"
          />
          <input
            value={limitInput}
            type="number"
            min={MIN_LIMIT}
            max={MAX_LIMIT}
            onChange={(event) => setLimitInput(event.target.value)}
            style={{ width: 120 }}
          />
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
      </Panel>
    </ScopeGate>
  );
}

function AuditTable({ rows }: { rows: ConfigAuditItemDTO[] }) {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr>
          <th align="left">When</th>
          <th align="left">Actor</th>
          <th align="left">Tenant</th>
          <th align="left">Action</th>
          <th align="left">Resource</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id} style={{ borderTop: '1px solid #e2e8f0' }}>
            <td>{new Date(row.created_at).toLocaleString()}</td>
            <td>{row.actor}</td>
            <td>{row.tenant_id ?? 'global'}</td>
            <td>{row.action}</td>
            <td>{row.resource_type}</td>
          </tr>
        ))}
      </tbody>
    </table>
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

  return (
    <ScopeGate
      allowed={canRead}
      title="Audit Trail Restricted"
      message="This session is missing control:tenants:read or control:config:read, so config audit history cannot be shown."
    >
      <Panel title="Configuration Audit Trail">
        <div style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
          <input
            value={tenantFilter}
            onChange={(event) => setTenantFilter(event.target.value)}
            placeholder="tenant filter (optional)"
          />
          <input
            value={limitInput}
            type="number"
            min={MIN_LIMIT}
            max={MAX_LIMIT}
            onChange={(event) => setLimitInput(event.target.value)}
            style={{ width: 120 }}
          />
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
      </Panel>
    </ScopeGate>
  );
}

export function App() {
  const { status, token, username, tenantId, scopes } = useSessionBootstrap();

  const client = useMemo(() => {
    if (!token) {
      return null;
    }
    return new ControlApiClient(CONTROL_API_BASE_URL, token);
  }, [token]);

  if (status === 'loading') {
    return (
      <OpsShell title="Authentication Required">
        <EnvironmentChecklist />
        <Panel title="Checking Monitoring Session">
          <p>Verifying the shared monitoring sign-in before opening the ops console.</p>
        </Panel>
      </OpsShell>
    );
  }

  if (!client || status !== 'ready') {
    return (
      <OpsShell title="Authentication Required">
        <EnvironmentChecklist />
        <AuthRequiredPanel invalidSession={status === 'invalid'} />
      </OpsShell>
    );
  }

  return (
    <OpsShell
      title="Operations Control Plane"
      actions={
        <div style={{ display: 'flex', gap: 12 }}>
          <span>
            {username ?? 'operator'} · {tenantId}
          </span>
          <a href={TENANT_CONSOLE_URL}>Open Tenant Console</a>
          <a href={MONITORING_APP_URL}>Open Monitoring App</a>
        </div>
      }
    >
      <EnvironmentChecklist />
      <Panel title="Session Capabilities">
        <p>Current token scopes:</p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {scopes.length > 0 ? scopes.map((scope) => <Badge key={scope} value={scope} />) : <span>No scopes found.</span>}
        </div>
      </Panel>
      <Navigation />
      <Routes>
        <Route path="/" element={<Navigate to="/ops/tenants" replace />} />
        <Route path="/ops/tenants" element={<TenantsPage client={client} scopes={scopes} />} />
        <Route path="/ops/connectors" element={<ConnectorsPage client={client} scopes={scopes} />} />
        <Route path="/ops/delivery" element={<DeliveryPage client={client} scopes={scopes} />} />
        <Route path="/ops/audit" element={<AuditPage client={client} scopes={scopes} />} />
        <Route path="*" element={<Navigate to="/ops/tenants" replace />} />
      </Routes>
    </OpsShell>
  );
}
