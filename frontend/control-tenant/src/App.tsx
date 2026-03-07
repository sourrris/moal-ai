import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { Navigate, NavLink, Route, Routes } from 'react-router-dom';

import { ControlApiClient } from '../../packages/control-api-client/src/client';
import type { TenantConfigurationDTO } from '../../packages/control-api-client/src/types';
import { buildMonitoringLoginUrl, consumeSessionFromUrl } from '../../packages/control-auth/src/handoff';
import { parseAuthSession } from '../../packages/control-auth/src/session';
import { getTenantPageMeta, TENANT_HOME_PATH, TENANT_PAGE_META } from './page-meta';
import {
  Badge,
  Button,
  ConsolePageFrame,
  ControlShell,
  DataPanel,
  DensityToggle,
  DetailItem,
  DetailList,
  Input,
  MetricCard,
  QueryStatus,
  Select,
  StatusBanner,
  TextArea,
  buttonClassName,
  cn,
  useDensityPreference
} from './ui';

const CONTROL_API_BASE_URL = import.meta.env.VITE_CONTROL_API_BASE_URL ?? 'http://control-api.localhost';
const MONITORING_APP_URL = import.meta.env.VITE_MONITORING_APP_URL ?? 'http://app.localhost';
const MONITORING_API_BASE_URL = import.meta.env.VITE_MONITORING_API_BASE_URL ?? 'http://api.localhost';

type SessionState = {
  token: string | null;
  username: string | null;
  tenantId: string;
};

type SessionBootstrapState = SessionState & {
  status: 'loading' | 'ready' | 'missing';
};

function getSessionState(): SessionState {
  const handedOffSession = consumeSessionFromUrl();
  if (handedOffSession.token) {
    return {
      token: handedOffSession.token,
      username: handedOffSession.username,
      tenantId: handedOffSession.tenantId ?? 'tenant-alpha'
    };
  }
  const token = window.localStorage.getItem('risk_token');
  const username = window.localStorage.getItem('risk_username');
  const session = parseAuthSession(token, username);
  return {
    token: session.token,
    username: session.username,
    tenantId: session.tenantId ?? 'tenant-alpha'
  };
}

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

  const session = parseAuthSession(payload.access_token, window.localStorage.getItem('risk_username'));
  if (!session.token) {
    return null;
  }

  window.localStorage.setItem('risk_token', session.token);
  if (session.username) {
    window.localStorage.setItem('risk_username', session.username);
  }

  return {
    token: session.token,
    username: session.username,
    tenantId: session.tenantId ?? 'tenant-alpha'
  };
}

function useSessionBootstrap(): SessionBootstrapState {
  const [state, setState] = useState<SessionBootstrapState>(() => {
    const current = getSessionState();
    if (current.token) {
      return { ...current, status: 'ready' };
    }
    return { ...current, status: 'loading' };
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
        if (session) {
          setState({ ...session, status: 'ready' });
          return;
        }
        setState({ token: null, username: null, tenantId: 'tenant-alpha', status: 'missing' });
      })
      .catch(() => {
        if (!cancelled) {
          setState({ token: null, username: null, tenantId: 'tenant-alpha', status: 'missing' });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [state.status]);

  return state;
}

async function rawRequest<T>(token: string, path: string, options?: { method?: string; body?: unknown }): Promise<T> {
  const response = await fetch(`${CONTROL_API_BASE_URL}${path}`, {
    method: options?.method ?? 'GET',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`
    },
    body: options?.body ? JSON.stringify(options.body) : undefined
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Request failed (${response.status}): ${detail || response.statusText}`);
  }

  return response.json() as Promise<T>;
}

function navigationLinkClassName(isActive: boolean) {
  return cn('control-nav__link', isActive && 'control-nav__link--active');
}

function Navigation() {
  return (
    <nav className="control-nav" aria-label="Tenant workspace sections">
      {TENANT_PAGE_META.map((item) => (
        <NavLink key={item.path} to={item.path} className={({ isActive }) => navigationLinkClassName(isActive)}>
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}

function AuthRequiredPanel() {
  return (
    <DataPanel title="Authentication Required" description="This workspace reuses the shared monitoring auth cookies.">
      <p data-testid="auth-required-message" className="muted">
        Sign in through the monitoring app first. This console reuses the shared monitoring auth cookies.
      </p>
      <div className="control-responsive-actions">
        <a className={buttonClassName('primary')} href={buildMonitoringLoginUrl(MONITORING_APP_URL, window.location.href)}>
          Open Monitoring Login
        </a>
      </div>
    </DataPanel>
  );
}

function OverviewPage({ client, tenantId }: { client: ControlApiClient; tenantId: string }) {
  const configQuery = useQuery({
    queryKey: ['tenant-config', tenantId],
    queryFn: () => client.getTenantConfiguration(tenantId)
  });
  const connectorsQuery = useQuery({
    queryKey: ['connector-catalog'],
    queryFn: () => client.listConnectorsCatalog()
  });
  const reconQuery = useQuery({
    queryKey: ['recon-ingestion', tenantId],
    queryFn: () => client.getIngestionReconciliation(tenantId)
  });
  const meta = getTenantPageMeta('/workspace/overview');

  const config = configQuery.data;
  const reconciliation = reconQuery.data;

  return (
    <ConsolePageFrame
      title={meta.title}
      subtitle={meta.subtitle}
      chips={<Badge variant="info">{tenantId}</Badge>}
    >
      <div className="control-summary-grid">
        <MetricCard label="Config version" value={config ? String(config.version) : '...'} meta="latest saved config" />
        <MetricCard
          label="Anomaly threshold"
          value={config?.anomaly_threshold != null ? String(config.anomaly_threshold) : 'default'}
          meta="tenant effective"
        />
        <MetricCard label="Pinned model" value={config?.model_version ?? 'global active'} meta="serving policy" />
        <MetricCard
          label="Mismatch count"
          value={reconciliation ? String(reconciliation.mismatch_count) : '...'}
          meta="latest reconciliation"
        />
      </div>

      <div className="control-grid-two">
        <DataPanel
          title="Tenant Posture"
          description="Current configuration values and serving posture for this tenant workspace."
          badge={config ? <Badge variant="success">v{config.version}</Badge> : <Badge variant="info">loading</Badge>}
        >
          {configQuery.isPending && !config ? <QueryStatus state="loading" subject="tenant posture" /> : null}
          {configQuery.isError ? (
            <QueryStatus state="error" subject="tenant posture" error={(configQuery.error as Error).message} />
          ) : null}
          {config ? (
            <DetailList>
              <DetailItem label="Tenant" value={config.tenant_id} />
              <DetailItem label="Enabled connectors" value={String(config.enabled_connectors.length)} />
              <DetailItem label="Updated at" value={new Date(config.updated_at).toLocaleString()} />
              <DetailItem label="Rule overrides" value={String(Object.keys(config.rule_overrides_json ?? {}).length)} />
            </DetailList>
          ) : null}
        </DataPanel>

        <DataPanel
          title="Latest Reconciliation Snapshot"
          description="Most recent ingestion and delivery reconciliation totals for this tenant."
          badge={
            reconciliation ? <Badge variant={reconciliation.mismatch_count > 0 ? 'warning' : 'success'}>live snapshot</Badge> : null
          }
        >
          {reconQuery.isPending && !reconciliation ? <QueryStatus state="loading" subject="reconciliation snapshot" /> : null}
          {reconQuery.isError ? (
            <QueryStatus
              state="error"
              subject="reconciliation snapshot"
              error={(reconQuery.error as Error).message}
            />
          ) : null}
          {reconciliation ? (
            <DetailList>
              <DetailItem label="Ingested events" value={reconciliation.ingested_events} />
              <DetailItem label="Processed decisions" value={reconciliation.processed_decisions} />
              <DetailItem label="Raised alerts" value={reconciliation.raised_alerts} />
              <DetailItem label="Delivered alerts" value={reconciliation.delivered_alerts} />
            </DetailList>
          ) : null}
        </DataPanel>
      </div>

      <DataPanel
        title="Connector Health Catalog"
        description="Shared feed availability and whether each source is globally enabled."
        badge={connectorsQuery.data ? <Badge variant="info">{connectorsQuery.data.length} sources</Badge> : null}
      >
        {connectorsQuery.isPending && !connectorsQuery.data ? <QueryStatus state="loading" subject="connector catalog" /> : null}
        {connectorsQuery.isError ? (
          <QueryStatus state="error" subject="connector catalog" error={(connectorsQuery.error as Error).message} />
        ) : null}
        {connectorsQuery.data && connectorsQuery.data.length === 0 ? <QueryStatus state="empty" subject="connector catalog" /> : null}
        {connectorsQuery.data && connectorsQuery.data.length > 0 ? (
          <div className="control-table-wrap">
            <table className="control-table">
              <thead>
                <tr>
                  <th scope="col">Source</th>
                  <th scope="col">Type</th>
                  <th scope="col">Enabled</th>
                  <th scope="col">Latest status</th>
                  <th scope="col">Latest run</th>
                </tr>
              </thead>
              <tbody>
                {connectorsQuery.data.map((item) => (
                  <tr key={item.source_name}>
                    <td className="mono">{item.source_name}</td>
                    <td>{item.source_type}</td>
                    <td>
                      <Badge variant={item.enabled ? 'success' : 'warning'}>{item.enabled ? 'enabled' : 'disabled'}</Badge>
                    </td>
                    <td>{item.latest_status ?? 'n/a'}</td>
                    <td>{item.latest_run_at ? new Date(item.latest_run_at).toLocaleString() : 'n/a'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </DataPanel>
    </ConsolePageFrame>
  );
}

function ConnectorsPage({ client, tenantId }: { client: ControlApiClient; tenantId: string }) {
  const queryClient = useQueryClient();
  const configQuery = useQuery({
    queryKey: ['tenant-config-connectors', tenantId],
    queryFn: () => client.getTenantConfiguration(tenantId)
  });
  const catalogQuery = useQuery({
    queryKey: ['connector-catalog-connectors'],
    queryFn: () => client.listConnectorsCatalog()
  });
  const [selected, setSelected] = useState<string[]>([]);

  const saveMutation = useMutation({
    mutationFn: (payload: { enabled_connectors: string[]; expected_version: number }) =>
      client.updateTenantConfiguration(tenantId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tenant-config-connectors', tenantId] });
      queryClient.invalidateQueries({ queryKey: ['tenant-config', tenantId] });
    }
  });

  const current = configQuery.data;
  const catalog = catalogQuery.data ?? [];
  const effectiveSelected = selected.length > 0 ? selected : current?.enabled_connectors ?? [];
  const meta = getTenantPageMeta('/workspace/config/connectors');

  return (
    <ConsolePageFrame
      title={meta.title}
      subtitle={meta.subtitle}
      chips={<Badge variant="info">{tenantId}</Badge>}
    >
      <DataPanel
        title="Connector Assignment"
        description="Select the shared intelligence feeds allowed for this tenant. Empty selection preserves worker defaults."
        badge={current ? <Badge variant="success">v{current.version}</Badge> : null}
      >
        {configQuery.isPending || catalogQuery.isPending ? <QueryStatus state="loading" subject="connector assignment" /> : null}
        {configQuery.isError ? (
          <QueryStatus state="error" subject="connector assignment" error={(configQuery.error as Error).message} />
        ) : null}
        {catalogQuery.isError ? (
          <QueryStatus state="error" subject="connector catalog" error={(catalogQuery.error as Error).message} />
        ) : null}

        {catalog.length > 0 ? (
          <div className="control-grid-two">
            {catalog.map((item) => (
              <label key={item.source_name} className="control-list__item">
                <div className="control-inline-actions">
                  <input
                    type="checkbox"
                    checked={effectiveSelected.includes(item.source_name)}
                    onChange={(event) => {
                      setSelected((prev) => {
                        const base = prev.length > 0 ? prev : current?.enabled_connectors ?? [];
                        if (event.target.checked) {
                          return [...new Set([...base, item.source_name])];
                        }
                        return base.filter((name) => name !== item.source_name);
                      });
                    }}
                  />
                  <strong>{item.source_name}</strong>
                  <Badge variant={item.enabled ? 'success' : 'warning'}>{item.enabled ? 'global on' : 'global off'}</Badge>
                </div>
                <span className="muted">
                  {item.source_type} feed {item.latest_status ? `· latest status ${item.latest_status}` : ''}
                </span>
              </label>
            ))}
          </div>
        ) : null}

        <div className="control-responsive-actions">
          <Button
            variant="primary"
            onClick={() => {
              if (!current) {
                return;
              }
              saveMutation.mutate({ enabled_connectors: effectiveSelected, expected_version: current.version });
            }}
            disabled={!current || saveMutation.isPending}
          >
            {saveMutation.isPending ? 'Saving...' : 'Save Connector Policy'}
          </Button>
        </div>

        {saveMutation.isError ? <StatusBanner variant="error">{(saveMutation.error as Error).message}</StatusBanner> : null}
        {saveMutation.isSuccess ? (
          <StatusBanner variant="success">Connector policy saved for {tenantId}.</StatusBanner>
        ) : null}
      </DataPanel>
    </ConsolePageFrame>
  );
}

function RiskPolicyPage({ client, tenantId }: { client: ControlApiClient; tenantId: string }) {
  const queryClient = useQueryClient();
  const configQuery = useQuery({
    queryKey: ['tenant-config-risk', tenantId],
    queryFn: () => client.getTenantConfiguration(tenantId)
  });
  const [threshold, setThreshold] = useState('');
  const [highAmountThreshold, setHighAmountThreshold] = useState('');

  const saveMutation = useMutation({
    mutationFn: (payload: Partial<TenantConfigurationDTO> & { expected_version: number }) =>
      client.updateTenantConfiguration(tenantId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tenant-config-risk', tenantId] });
      queryClient.invalidateQueries({ queryKey: ['tenant-config', tenantId] });
    }
  });

  const current = configQuery.data;
  const meta = getTenantPageMeta('/workspace/config/risk-policy');

  return (
    <ConsolePageFrame
      title={meta.title}
      subtitle={meta.subtitle}
      chips={<Badge variant="info">{tenantId}</Badge>}
    >
      <DataPanel
        title="Anomaly Threshold And Rule Overrides"
        description="Adjust tenant-specific thresholds while preserving the shared scoring pipeline."
        badge={current ? <Badge variant="success">v{current.version}</Badge> : null}
      >
        {configQuery.isPending && !current ? <QueryStatus state="loading" subject="risk policy" /> : null}
        {configQuery.isError ? (
          <QueryStatus state="error" subject="risk policy" error={(configQuery.error as Error).message} />
        ) : null}

        <div className="control-field-grid">
          <div className="control-field">
            <label htmlFor="anomaly-threshold">Anomaly threshold</label>
            <Input
              id="anomaly-threshold"
              value={threshold || String(current?.anomaly_threshold ?? '')}
              onChange={(event) => setThreshold(event.target.value)}
              placeholder="0.85"
            />
            <span className="control-field__help">Leave empty to preserve the current configured value.</span>
          </div>
          <div className="control-field">
            <label htmlFor="high-amount-threshold">High amount threshold</label>
            <Input
              id="high-amount-threshold"
              value={highAmountThreshold || String(current?.rule_overrides_json.high_amount_threshold ?? '')}
              onChange={(event) => setHighAmountThreshold(event.target.value)}
              placeholder="10000"
            />
            <span className="control-field__help">Tenant override for the high amount rule.</span>
          </div>
        </div>

        <div className="control-responsive-actions">
          <Button
            variant="primary"
            onClick={() => {
              if (!current) {
                return;
              }
              saveMutation.mutate({
                anomaly_threshold: threshold ? Number(threshold) : current.anomaly_threshold,
                rule_overrides_json: {
                  ...(current.rule_overrides_json ?? {}),
                  ...(highAmountThreshold ? { high_amount_threshold: Number(highAmountThreshold) } : {})
                },
                expected_version: current.version
              });
            }}
            disabled={!current || saveMutation.isPending}
          >
            {saveMutation.isPending ? 'Saving...' : 'Save Risk Policy'}
          </Button>
        </div>

        {saveMutation.isError ? <StatusBanner variant="error">{(saveMutation.error as Error).message}</StatusBanner> : null}
        {saveMutation.isSuccess ? <StatusBanner variant="success">Risk policy saved for {tenantId}.</StatusBanner> : null}
      </DataPanel>
    </ConsolePageFrame>
  );
}

function ModelPolicyPage({ client, tenantId }: { client: ControlApiClient; tenantId: string }) {
  const queryClient = useQueryClient();
  const configQuery = useQuery({
    queryKey: ['tenant-config-model', tenantId],
    queryFn: () => client.getTenantConfiguration(tenantId)
  });
  const [modelVersion, setModelVersion] = useState('');

  const saveMutation = useMutation({
    mutationFn: (payload: Partial<TenantConfigurationDTO> & { expected_version: number }) =>
      client.updateTenantConfiguration(tenantId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tenant-config-model', tenantId] });
      queryClient.invalidateQueries({ queryKey: ['tenant-config', tenantId] });
    }
  });

  const current = configQuery.data;
  const meta = getTenantPageMeta('/workspace/config/model-policy');

  return (
    <ConsolePageFrame
      title={meta.title}
      subtitle={meta.subtitle}
      chips={<Badge variant="info">{tenantId}</Badge>}
    >
      <DataPanel
        title="Tenant Model Policy"
        description="Pin a tenant to a specific model version or follow the global active model."
        badge={current ? <Badge variant="success">v{current.version}</Badge> : null}
      >
        {configQuery.isPending && !current ? <QueryStatus state="loading" subject="model policy" /> : null}
        {configQuery.isError ? (
          <QueryStatus state="error" subject="model policy" error={(configQuery.error as Error).message} />
        ) : null}

        <div className="control-field">
          <label htmlFor="model-version">Pinned model version</label>
          <Input
            id="model-version"
            value={modelVersion || current?.model_version || ''}
            onChange={(event) => setModelVersion(event.target.value)}
            placeholder="20260301000000"
          />
          <span className="control-field__help">Leave empty to follow the global active model version.</span>
        </div>

        <div className="control-responsive-actions">
          <Button
            variant="primary"
            onClick={() => {
              if (!current) {
                return;
              }
              saveMutation.mutate({
                model_version: modelVersion || null,
                expected_version: current.version
              });
            }}
            disabled={!current || saveMutation.isPending}
          >
            {saveMutation.isPending ? 'Saving...' : 'Save Model Policy'}
          </Button>
        </div>

        {saveMutation.isError ? <StatusBanner variant="error">{(saveMutation.error as Error).message}</StatusBanner> : null}
        {saveMutation.isSuccess ? <StatusBanner variant="success">Model policy saved for {tenantId}.</StatusBanner> : null}
      </DataPanel>
    </ConsolePageFrame>
  );
}

function TestLabPage({ token, tenantId }: { token: string; tenantId: string }) {
  const [eventsJson, setEventsJson] = useState(
    JSON.stringify(
      [
        {
          idempotency_key: `control-test-${Date.now()}`,
          source: 'control_test',
          event_type: 'transaction',
          transaction: {
            transaction_id: `txn-${Date.now()}`,
            amount: 12450.12,
            currency: 'USD',
            source_country: 'US',
            destination_country: 'GB',
            metadata: { channel: 'control-tenant' }
          },
          occurred_at: new Date().toISOString()
        }
      ],
      null,
      2
    )
  );
  const [runResult, setRunResult] = useState('');
  const [runError, setRunError] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const meta = getTenantPageMeta('/workspace/test-lab');

  return (
    <ConsolePageFrame
      title={meta.title}
      subtitle={meta.subtitle}
      chips={<Badge variant="info">{tenantId}</Badge>}
    >
      <DataPanel title="Upload And Run" description="Submit a JSON event set and execute a tenant-scoped deterministic test run.">
        <div className="control-field">
          <label htmlFor="test-lab-json">Event payload</label>
          <TextArea id="test-lab-json" value={eventsJson} onChange={(event) => setEventsJson(event.target.value)} />
        </div>

        <div className="control-responsive-actions">
          <Button
            variant="primary"
            onClick={async () => {
              setRunError('');
              setIsRunning(true);
              try {
                const events = JSON.parse(eventsJson) as unknown[];
                const upload = await rawRequest<{ dataset_id: string }>(
                  token,
                  `/control/v1/tenants/${tenantId}/test-datasets/uploads`,
                  {
                    method: 'POST',
                    body: {
                      name: `tenant-test-${Date.now()}`,
                      source_type: 'json',
                      events
                    }
                  }
                );
                const run = await rawRequest<{ run_id: string }>(token, `/control/v1/tenants/${tenantId}/test-runs`, {
                  method: 'POST',
                  body: { dataset_id: upload.dataset_id }
                });
                setRunResult(JSON.stringify(run, null, 2));
              } catch (error) {
                setRunResult('');
                setRunError(error instanceof Error ? error.message : 'Unable to execute test run.');
              } finally {
                setIsRunning(false);
              }
            }}
            disabled={isRunning}
          >
            {isRunning ? 'Uploading...' : 'Upload And Run'}
          </Button>
        </div>

        {runError ? <StatusBanner variant="error">{runError}</StatusBanner> : null}
        {runResult ? <pre className="control-code-result">{runResult}</pre> : null}
      </DataPanel>
    </ConsolePageFrame>
  );
}

function AlertRoutingPage({ client, token, tenantId }: { client: ControlApiClient; token: string; tenantId: string }) {
  const queryClient = useQueryClient();
  const destinationsQuery = useQuery({
    queryKey: ['alert-destinations', tenantId],
    queryFn: () => client.listAlertDestinations(tenantId)
  });
  const [channel, setChannel] = useState<'webhook' | 'email' | 'slack'>('webhook');
  const [name, setName] = useState('');
  const [target, setTarget] = useState('');
  const [actionMessage, setActionMessage] = useState('');
  const [actionError, setActionError] = useState('');

  const createMutation = useMutation({
    mutationFn: async () => {
      const config =
        channel === 'webhook' ? { url: target } : channel === 'slack' ? { webhook_url: target } : { to: [target] };
      return client.createAlertDestination(tenantId, {
        channel,
        name,
        enabled: true,
        config
      });
    },
    onSuccess: () => {
      setName('');
      setTarget('');
      setActionError('');
      setActionMessage('Alert destination created.');
      queryClient.invalidateQueries({ queryKey: ['alert-destinations', tenantId] });
    }
  });

  const meta = getTenantPageMeta('/workspace/alert-routing');

  return (
    <ConsolePageFrame
      title={meta.title}
      subtitle={meta.subtitle}
      chips={<Badge variant="info">{tenantId}</Badge>}
    >
      <div className="control-grid-two">
        <DataPanel title="Create Destination" description="Add a verified route for email, webhook, or Slack delivery.">
          <div className="control-field">
            <label htmlFor="destination-channel">Channel</label>
            <Select
              id="destination-channel"
              value={channel}
              onChange={(event) => setChannel(event.target.value as typeof channel)}
            >
              <option value="webhook">Webhook</option>
              <option value="email">Email</option>
              <option value="slack">Slack</option>
            </Select>
          </div>
          <div className="control-field">
            <label htmlFor="destination-name">Name</label>
            <Input id="destination-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Primary SOC route" />
          </div>
          <div className="control-field">
            <label htmlFor="destination-target">Target</label>
            <Input
              id="destination-target"
              value={target}
              onChange={(event) => setTarget(event.target.value)}
              placeholder={channel === 'email' ? 'team@company.com' : 'https://...'}
            />
          </div>

          <div className="control-responsive-actions">
            <Button variant="primary" onClick={() => createMutation.mutate()} disabled={createMutation.isPending || !name || !target}>
              {createMutation.isPending ? 'Creating...' : 'Create Destination'}
            </Button>
          </div>

          {createMutation.isError ? <StatusBanner variant="error">{(createMutation.error as Error).message}</StatusBanner> : null}
          {actionMessage ? <StatusBanner variant="success">{actionMessage}</StatusBanner> : null}
          {actionError ? <StatusBanner variant="error">{actionError}</StatusBanner> : null}
        </DataPanel>

        <DataPanel
          title="Configured Destinations"
          description="Verify routes and send test traffic to validate your current delivery configuration."
          badge={destinationsQuery.data ? <Badge variant="info">{destinationsQuery.data.length} routes</Badge> : null}
        >
          {destinationsQuery.isPending && !destinationsQuery.data ? <QueryStatus state="loading" subject="alert destinations" /> : null}
          {destinationsQuery.isError ? (
            <QueryStatus state="error" subject="alert destinations" error={(destinationsQuery.error as Error).message} />
          ) : null}
          {destinationsQuery.data && destinationsQuery.data.length === 0 ? <QueryStatus state="empty" subject="alert destinations" /> : null}
          {destinationsQuery.data && destinationsQuery.data.length > 0 ? (
            <ul className="control-list">
              {destinationsQuery.data.map((item) => (
                <li key={item.destination_id} className="control-list__item">
                  <div className="control-inline-actions">
                    <strong>{item.name}</strong>
                    <Badge variant="neutral">{item.channel}</Badge>
                    <Badge variant={item.verification_status === 'verified' ? 'success' : 'warning'}>
                      {item.verification_status}
                    </Badge>
                  </div>
                  <span className="muted">Updated {new Date(item.updated_at).toLocaleString()}</span>
                  <div className="control-list__item-actions">
                    <Button
                      onClick={async () => {
                        setActionMessage('');
                        setActionError('');
                        try {
                          await client.verifyAlertDestination(tenantId, item.destination_id);
                          setActionMessage(`Verification requested for ${item.name}.`);
                          queryClient.invalidateQueries({ queryKey: ['alert-destinations', tenantId] });
                        } catch (error) {
                          setActionError(error instanceof Error ? error.message : 'Unable to verify destination.');
                        }
                      }}
                    >
                      Verify
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={async () => {
                        setActionMessage('');
                        setActionError('');
                        try {
                          await rawRequest(token, `/control/v1/tenants/${tenantId}/alert-routing/test`, {
                            method: 'POST',
                            body: { severity: 'critical', payload: { route: item.destination_id } }
                          });
                          setActionMessage(`Test alert sent to ${item.name}.`);
                        } catch (error) {
                          setActionError(error instanceof Error ? error.message : 'Unable to send test alert.');
                        }
                      }}
                    >
                      Send Test
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
        </DataPanel>
      </div>
    </ConsolePageFrame>
  );
}

function ReconciliationPage({ client, tenantId }: { client: ControlApiClient; tenantId: string }) {
  const reconQuery = useQuery({
    queryKey: ['reconciliation-page', tenantId],
    queryFn: () => client.getIngestionReconciliation(tenantId)
  });
  const meta = getTenantPageMeta('/workspace/reconciliation');

  return (
    <ConsolePageFrame
      title={meta.title}
      subtitle={meta.subtitle}
      chips={<Badge variant="info">{tenantId}</Badge>}
    >
      <DataPanel
        title="Reconciliation Reports"
        description="Inspect current counts and export the tenant reconciliation report."
        badge={
          reconQuery.data ? (
            <Badge variant={reconQuery.data.mismatch_count > 0 ? 'warning' : 'success'}>latest snapshot</Badge>
          ) : null
        }
      >
        {reconQuery.isPending && !reconQuery.data ? <QueryStatus state="loading" subject="reconciliation" /> : null}
        {reconQuery.isError ? (
          <QueryStatus state="error" subject="reconciliation" error={(reconQuery.error as Error).message} />
        ) : null}
        {reconQuery.data ? (
          <>
            <div className="control-summary-grid">
              <MetricCard label="Ingested" value={String(reconQuery.data.ingested_events)} meta="pipeline input" />
              <MetricCard label="Processed" value={String(reconQuery.data.processed_decisions)} meta="decision output" />
              <MetricCard label="Raised alerts" value={String(reconQuery.data.raised_alerts)} meta="control handoff" />
              <MetricCard label="Delivered alerts" value={String(reconQuery.data.delivered_alerts)} meta="channel success" />
            </div>
            <DetailList>
              <DetailItem label="Failed deliveries" value={reconQuery.data.failed_deliveries} />
              <DetailItem label="Mismatch count" value={reconQuery.data.mismatch_count} />
              <DetailItem label="From" value={new Date(reconQuery.data.from_ts).toLocaleString()} />
              <DetailItem label="To" value={new Date(reconQuery.data.to_ts).toLocaleString()} />
            </DetailList>
            <div className="control-responsive-actions">
              <a
                className={buttonClassName('secondary')}
                href={`${CONTROL_API_BASE_URL}/control/v1/tenants/${tenantId}/reconciliation/export`}
                target="_blank"
                rel="noreferrer"
              >
                Export CSV
              </a>
            </div>
          </>
        ) : null}
      </DataPanel>
    </ConsolePageFrame>
  );
}

export function App() {
  const { status, token, username, tenantId } = useSessionBootstrap();
  const [density, setDensity] = useDensityPreference('control_tenant_density');

  const client = useMemo(() => {
    if (!token) {
      return null;
    }
    return new ControlApiClient(CONTROL_API_BASE_URL, token);
  }, [token]);

  const brand = (
    <NavLink to={TENANT_HOME_PATH} className="control-brand">
      <span className="control-brand__mark">tn</span>
      <span className="control-brand__copy">
        <span className="control-brand__eyebrow">Tenant Workspace</span>
        <span className="control-brand__name">Aegis Tenant Console</span>
      </span>
    </NavLink>
  );

  if (status === 'loading') {
    return (
      <ControlShell brand={brand}>
        <DataPanel title="Checking Monitoring Session" description="Verifying the shared monitoring sign-in before opening the tenant console.">
          <p className="muted">Verifying the shared monitoring sign-in before opening the tenant console.</p>
        </DataPanel>
      </ControlShell>
    );
  }

  if (!token || !client) {
    return (
      <ControlShell brand={brand}>
        <AuthRequiredPanel />
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
          <a className={buttonClassName('ghost')} href={MONITORING_APP_URL}>
            Open Monitoring App
          </a>
        </>
      }
      utilityBar={
        <div className="control-responsive-actions">
          <Badge variant="success">workspace ready</Badge>
          <Badge variant="info">{tenantId}</Badge>
          <DensityToggle value={density} onChange={setDensity} />
        </div>
      }
    >
      <Routes>
        <Route path={TENANT_HOME_PATH} element={<OverviewPage client={client} tenantId={tenantId} />} />
        <Route path="/workspace/config/connectors" element={<ConnectorsPage client={client} tenantId={tenantId} />} />
        <Route path="/workspace/config/risk-policy" element={<RiskPolicyPage client={client} tenantId={tenantId} />} />
        <Route path="/workspace/config/model-policy" element={<ModelPolicyPage client={client} tenantId={tenantId} />} />
        <Route path="/workspace/test-lab" element={<TestLabPage token={token} tenantId={tenantId} />} />
        <Route path="/workspace/alert-routing" element={<AlertRoutingPage client={client} token={token} tenantId={tenantId} />} />
        <Route path="/workspace/reconciliation" element={<ReconciliationPage client={client} tenantId={tenantId} />} />
        <Route path="/" element={<Navigate to={TENANT_HOME_PATH} replace />} />
        <Route path="*" element={<Navigate to={TENANT_HOME_PATH} replace />} />
      </Routes>
    </ControlShell>
  );
}
