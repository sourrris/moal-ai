import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { Navigate, NavLink, Route, Routes } from 'react-router-dom';

import { ControlApiClient } from '../../packages/control-api-client/src/client';
import type { TenantConfigurationDTO } from '../../packages/control-api-client/src/types';
import { parseAuthSession } from '../../packages/control-auth/src/session';
import { AppShell, KeyValue, Section } from './ui';

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

function Navigation() {
  return (
    <nav style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
      <NavLink to="/workspace/overview">Overview</NavLink>
      <NavLink to="/workspace/config/connectors">Connectors</NavLink>
      <NavLink to="/workspace/config/risk-policy">Risk Policy</NavLink>
      <NavLink to="/workspace/config/model-policy">Model Policy</NavLink>
      <NavLink to="/workspace/test-lab">Test Lab</NavLink>
      <NavLink to="/workspace/alert-routing">Alert Routing</NavLink>
      <NavLink to="/workspace/reconciliation">Reconciliation</NavLink>
    </nav>
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

  return (
    <>
      <Section title="Tenant Posture">
        {configQuery.data ? (
          <>
            <KeyValue label="Tenant" value={configQuery.data.tenant_id} />
            <KeyValue label="Config Version" value={configQuery.data.version} />
            <KeyValue label="Anomaly Threshold" value={String(configQuery.data.anomaly_threshold ?? 'default')} />
            <KeyValue label="Pinned Model" value={configQuery.data.model_version ?? 'global active'} />
          </>
        ) : (
          <p>Loading tenant posture...</p>
        )}
      </Section>

      <Section title="Connector Health Catalog">
        {connectorsQuery.data ? (
          <ul>
            {connectorsQuery.data.map((item) => (
              <li key={item.source_name}>
                {item.source_name} ({item.source_type}) - {item.enabled ? 'enabled' : 'disabled'}
              </li>
            ))}
          </ul>
        ) : (
          <p>Loading connector catalog...</p>
        )}
      </Section>

      <Section title="Latest Reconciliation Snapshot">
        {reconQuery.data ? (
          <>
            <KeyValue label="Ingested Events" value={reconQuery.data.ingested_events} />
            <KeyValue label="Processed Decisions" value={reconQuery.data.processed_decisions} />
            <KeyValue label="Raised Alerts" value={reconQuery.data.raised_alerts} />
            <KeyValue label="Delivered Alerts" value={reconQuery.data.delivered_alerts} />
            <KeyValue label="Mismatch Count" value={reconQuery.data.mismatch_count} />
          </>
        ) : (
          <p>Loading reconciliation snapshot...</p>
        )}
      </Section>
    </>
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

  return (
    <Section title="Connector Assignment">
      <p>Select allowed connectors for this tenant. Empty selection means worker default behavior.</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))', gap: 10 }}>
        {catalog.map((item) => (
          <label key={item.source_name} style={{ display: 'flex', gap: 8 }}>
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
            <span>{item.source_name}</span>
          </label>
        ))}
      </div>
      <button
        onClick={() => {
          if (!current) return;
          saveMutation.mutate({ enabled_connectors: effectiveSelected, expected_version: current.version });
        }}
        disabled={!current || saveMutation.isPending}
        style={{ marginTop: 12 }}
      >
        {saveMutation.isPending ? 'Saving...' : 'Save Connector Policy'}
      </button>
      {saveMutation.isError && <p style={{ color: '#b91c1c' }}>{(saveMutation.error as Error).message}</p>}
    </Section>
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

  return (
    <Section title="Anomaly Threshold And Rule Overrides">
      <div style={{ display: 'grid', gap: 10, maxWidth: 420 }}>
        <label>
          Anomaly threshold
          <input
            style={{ width: '100%' }}
            value={threshold || String(current?.anomaly_threshold ?? '')}
            onChange={(event) => setThreshold(event.target.value)}
            placeholder="0.85"
          />
        </label>
        <label>
          High amount threshold
          <input
            style={{ width: '100%' }}
            value={highAmountThreshold || String(current?.rule_overrides_json.high_amount_threshold ?? '')}
            onChange={(event) => setHighAmountThreshold(event.target.value)}
            placeholder="10000"
          />
        </label>
        <button
          onClick={() => {
            if (!current) return;
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
        </button>
      </div>
      {saveMutation.isError && <p style={{ color: '#b91c1c' }}>{(saveMutation.error as Error).message}</p>}
    </Section>
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

  return (
    <Section title="Tenant Model Policy">
      <p>Pin tenant model version to global active version or leave empty for global follow mode.</p>
      <div style={{ display: 'grid', gap: 10, maxWidth: 420 }}>
        <input
          value={modelVersion || current?.model_version || ''}
          onChange={(event) => setModelVersion(event.target.value)}
          placeholder="20260301000000"
        />
        <button
          onClick={() => {
            if (!current) return;
            saveMutation.mutate({
              model_version: modelVersion || null,
              expected_version: current.version
            });
          }}
          disabled={!current || saveMutation.isPending}
        >
          {saveMutation.isPending ? 'Saving...' : 'Save Model Policy'}
        </button>
      </div>
      {saveMutation.isError && <p style={{ color: '#b91c1c' }}>{(saveMutation.error as Error).message}</p>}
    </Section>
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
  const [runResult, setRunResult] = useState<string>('');

  return (
    <Section title="Test Lab">
      <p>Upload a test dataset and execute deterministic test runs against ingestion and decision pipelines.</p>
      <textarea
        style={{ width: '100%', minHeight: 280, fontFamily: 'monospace', fontSize: 13 }}
        value={eventsJson}
        onChange={(event) => setEventsJson(event.target.value)}
      />
      <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
        <button
          onClick={async () => {
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
          }}
        >
          Upload And Run
        </button>
      </div>
      {runResult && <pre style={{ whiteSpace: 'pre-wrap' }}>{runResult}</pre>}
    </Section>
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
      queryClient.invalidateQueries({ queryKey: ['alert-destinations', tenantId] });
    }
  });

  return (
    <Section title="Alert Routing">
      <div style={{ display: 'grid', gap: 10, maxWidth: 620 }}>
        <label>
          Channel
          <select value={channel} onChange={(event) => setChannel(event.target.value as typeof channel)}>
            <option value="webhook">Webhook</option>
            <option value="email">Email</option>
            <option value="slack">Slack</option>
          </select>
        </label>
        <label>
          Name
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Primary SOC route" />
        </label>
        <label>
          Target
          <input
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            placeholder={channel === 'email' ? 'team@company.com' : 'https://...'}
          />
        </label>
        <button onClick={() => createMutation.mutate()} disabled={createMutation.isPending || !name || !target}>
          {createMutation.isPending ? 'Creating...' : 'Create Destination'}
        </button>
      </div>

      <h3>Configured Destinations</h3>
      <ul>
        {(destinationsQuery.data ?? []).map((item) => (
          <li key={item.destination_id}>
            {item.name} ({item.channel}) - {item.verification_status}{' '}
            <button
              onClick={async () => {
                await client.verifyAlertDestination(tenantId, item.destination_id);
                queryClient.invalidateQueries({ queryKey: ['alert-destinations', tenantId] });
              }}
            >
              Verify
            </button>{' '}
            <button
              onClick={async () => {
                await rawRequest(token, `/control/v1/tenants/${tenantId}/alert-routing/test`, {
                  method: 'POST',
                  body: { severity: 'critical', payload: { route: item.destination_id } }
                });
              }}
            >
              Send Test
            </button>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function ReconciliationPage({ client, tenantId }: { client: ControlApiClient; tenantId: string }) {
  const reconQuery = useQuery({
    queryKey: ['reconciliation-page', tenantId],
    queryFn: () => client.getIngestionReconciliation(tenantId)
  });

  return (
    <Section title="Reconciliation Reports">
      {reconQuery.data ? (
        <>
          <KeyValue label="Ingested" value={reconQuery.data.ingested_events} />
          <KeyValue label="Processed" value={reconQuery.data.processed_decisions} />
          <KeyValue label="Raised Alerts" value={reconQuery.data.raised_alerts} />
          <KeyValue label="Delivered Alerts" value={reconQuery.data.delivered_alerts} />
          <KeyValue label="Failed Deliveries" value={reconQuery.data.failed_deliveries} />
          <KeyValue label="Mismatch" value={reconQuery.data.mismatch_count} />
          <a href={`${CONTROL_API_BASE_URL}/control/v1/tenants/${tenantId}/reconciliation/export`} target="_blank" rel="noreferrer">
            Export CSV
          </a>
        </>
      ) : (
        <p>Loading reconciliation...</p>
      )}
    </Section>
  );
}

export function App() {
  const { status, token, username, tenantId } = useSessionBootstrap();

  const client = useMemo(() => {
    if (!token) return null;
    return new ControlApiClient(CONTROL_API_BASE_URL, token);
  }, [token]);

  if (status === 'loading') {
    return (
      <AppShell title="Aegis Control Console">
        <Section title="Checking Monitoring Session">
          <p>Verifying the shared monitoring sign-in before opening the tenant console.</p>
        </Section>
      </AppShell>
    );
  }

  if (!token || !client) {
    return (
      <AppShell title="Aegis Control Console">
        <Section title="Authentication Required">
          <p>Sign in through the monitoring app first. This console reuses the shared monitoring auth cookies.</p>
          <a href={`${MONITORING_APP_URL}/login`}>Open Monitoring Login</a>
        </Section>
      </AppShell>
    );
  }

  return (
    <AppShell
      title="Aegis Tenant Control Console"
      actions={
        <div style={{ display: 'flex', gap: 12 }}>
          <span>{username ?? 'operator'} · {tenantId}</span>
          <a href={MONITORING_APP_URL}>Open Monitoring App</a>
        </div>
      }
    >
      <Navigation />
      <Routes>
        <Route path="/workspace/overview" element={<OverviewPage client={client} tenantId={tenantId} />} />
        <Route path="/workspace/config/connectors" element={<ConnectorsPage client={client} tenantId={tenantId} />} />
        <Route path="/workspace/config/risk-policy" element={<RiskPolicyPage client={client} tenantId={tenantId} />} />
        <Route path="/workspace/config/model-policy" element={<ModelPolicyPage client={client} tenantId={tenantId} />} />
        <Route path="/workspace/test-lab" element={<TestLabPage token={token} tenantId={tenantId} />} />
        <Route path="/workspace/alert-routing" element={<AlertRoutingPage client={client} token={token} tenantId={tenantId} />} />
        <Route path="/workspace/reconciliation" element={<ReconciliationPage client={client} tenantId={tenantId} />} />
        <Route path="*" element={<Navigate to="/workspace/overview" replace />} />
      </Routes>
    </AppShell>
  );
}
