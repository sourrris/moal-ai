import { useQuery } from '@tanstack/react-query';
import { Area, AreaChart, CartesianGrid, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { useAuth } from '../../app/state/auth-context';
import { useLiveAlertState } from '../../app/state/live-alerts-context';
import { useUI } from '../../app/state/ui-context';
import { fetchAlerts } from '../../shared/api/alerts';
import { fetchDataSourceRuns, fetchDataSourceStatus } from '../../shared/api/data-sources';
import { fetchOverviewMetrics } from '../../shared/api/overview';
import { formatDateTime } from '../../shared/lib/time';
import { Badge } from '../../shared/ui/badge';
import { DataPanel } from '../../shared/ui/DataPanel';
import { KpiCard } from '../../shared/ui/KpiCard';
import { DashboardPageFrame } from '../../widgets/layout/DashboardPageFrame';

function formatDuration(seconds: number | null | undefined) {
  if (seconds == null) {
    return 'n/a';
  }
  if (seconds < 60) {
    return `${seconds}s`;
  }
  if (seconds < 3600) {
    return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  }
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

function sourceStatusBadge(
  enabled: boolean,
  latestStatus: string | null,
  consecutiveFailures: number,
  freshnessSeconds: number | null | undefined,
  freshnessSloSeconds: number | null | undefined
) {
  if (!enabled) {
    return 'neutral' as const;
  }
  if (latestStatus === 'failed') {
    return 'critical' as const;
  }
  if (latestStatus === 'degraded' || consecutiveFailures > 0) {
    return 'warning' as const;
  }
  if (
    freshnessSeconds != null &&
    freshnessSloSeconds != null &&
    freshnessSloSeconds > 0 &&
    freshnessSeconds > freshnessSloSeconds
  ) {
    return 'warning' as const;
  }
  if (latestStatus === 'success' || latestStatus === 'partial' || latestStatus === 'noop') {
    return 'success' as const;
  }
  return 'info' as const;
}

function scrollToSection(id: string) {
  const target = document.getElementById(id);
  if (!target) {
    return;
  }
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  target.scrollIntoView({ behavior: prefersReducedMotion ? 'auto' : 'smooth', block: 'start' });
}

export function OverviewPage() {
  const { token } = useAuth();
  const { tenant, window, timezone } = useUI();
  const live = useLiveAlertState();

  const metricsQuery = useQuery({
    queryKey: ['overview-metrics', tenant, window],
    queryFn: async () => fetchOverviewMetrics(token!, tenant, window),
    enabled: Boolean(token),
    refetchInterval: live.connected && !live.stale ? false : 15_000,
    refetchIntervalInBackground: true
  });

  const criticalAlertsQuery = useQuery({
    queryKey: ['overview-critical-alerts', tenant, window],
    queryFn: async () =>
      fetchAlerts(token!, {
        tenant_id: tenant === 'all' ? undefined : tenant,
        severity: 'critical',
        limit: 10
      }),
    enabled: Boolean(token),
    refetchInterval: live.connected && !live.stale ? false : 15_000,
    refetchIntervalInBackground: true
  });

  const dataSourceStatusQuery = useQuery({
    queryKey: ['data-sources-status', tenant],
    queryFn: async () => fetchDataSourceStatus(token!),
    enabled: Boolean(token),
    refetchInterval: 20_000,
    refetchIntervalInBackground: true
  });

  const dataSourceRunsQuery = useQuery({
    queryKey: ['data-sources-runs', tenant],
    queryFn: async () => fetchDataSourceRuns(token!, 12),
    enabled: Boolean(token),
    refetchInterval: 20_000,
    refetchIntervalInBackground: true
  });

  if (metricsQuery.isLoading) {
    return <p className="muted">Loading overview metrics...</p>;
  }

  if (metricsQuery.isError || !metricsQuery.data) {
    return <p className="inline-error">Unable to load overview metrics.</p>;
  }

  const data = metricsQuery.data;
  const latestLiveMetric = live.metrics[0];

  const activeAnomalies = data.active_anomalies;
  const alertRate = latestLiveMetric?.total_alerts_1m != null ? latestLiveMetric.total_alerts_1m * 60 : data.alert_rate;
  const ingestionRate = latestLiveMetric?.total_events_1m != null ? latestLiveMetric.total_events_1m * 60 : data.ingestion_rate;

  const dataSourceStatuses = dataSourceStatusQuery.data ?? [];
  const dataSourceRuns = dataSourceRunsQuery.data ?? [];
  const series = data.timeseries.map((row) => ({
    time: formatDateTime(row.bucket, timezone),
    score: Number((row.avg_score ?? 0).toFixed(4)),
    threshold: Number((row.avg_threshold ?? 0).toFixed(4)),
    volume: row.anomaly_count
  }));

  return (
    <DashboardPageFrame
      chips={
        <Badge variant={live.connected ? (live.stale ? 'warning' : 'success') : 'critical'}>
          {live.connected ? (live.stale ? 'degraded stream' : 'live stream') : 'stream offline'}
        </Badge>
      }
    >
      <div className="kpi-grid">
        <KpiCard
          label="Active anomalies"
          value={String(activeAnomalies)}
          meta="current posture"
          onClick={() => scrollToSection('critical-alerts-section')}
        />
        <KpiCard
          label="Alert rate"
          value={`${alertRate.toFixed(2)} / hr`}
          meta={latestLiveMetric?.total_alerts_1m != null ? 'live adjusted' : 'snapshot'}
          onClick={() => scrollToSection('trend-section')}
        />
        <KpiCard
          label="Ingestion throughput"
          value={`${ingestionRate.toFixed(2)} / hr`}
          meta={latestLiveMetric?.total_events_1m != null ? 'live adjusted' : 'snapshot'}
          onClick={() => scrollToSection('sources-section')}
        />
        <KpiCard
          label="Failure rate"
          value={`${data.failure_rate.toFixed(2)}%`}
          meta={data.failure_rate > 1 ? 'watch closely' : 'within range'}
          trend={data.failure_rate > 1 ? 'down' : 'neutral'}
          onClick={() => scrollToSection('sources-section')}
        />
        <KpiCard
          label="Model health"
          value={`${data.model_health.toFixed(1)}%`}
          meta={data.model_health >= 95 ? 'healthy' : 'degraded'}
          trend={data.model_health >= 95 ? 'up' : 'down'}
          onClick={() => scrollToSection('trend-section')}
        />
        <KpiCard
          label="Live risk score"
          value={latestLiveMetric ? latestLiveMetric.risk_score.toFixed(3) : 'n/a'}
          meta={latestLiveMetric?.decision_latency_ms ? `latency ${latestLiveMetric.decision_latency_ms}ms` : 'awaiting live metric'}
          onClick={() => scrollToSection('critical-alerts-section')}
        />
      </div>

      <div id="trend-section" className="grid-two scroll-mt-40">
        <DataPanel title="Anomaly score vs threshold" description="Trendline for anomaly score, threshold, and volume context.">
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={series}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
              <XAxis dataKey="time" hide />
              <YAxis width={56} />
              <Tooltip
                contentStyle={{ borderRadius: 12, borderColor: '#e4e4e7', fontSize: 12 }}
                labelStyle={{ fontWeight: 600 }}
              />
              <Area type="monotone" dataKey="score" stroke="var(--accent)" fill="rgba(37,99,235,0.18)" />
              <Area type="monotone" dataKey="threshold" stroke="var(--status-warning)" fill="rgba(217,119,6,0.14)" />
            </AreaChart>
          </ResponsiveContainer>
        </DataPanel>

        <DataPanel title="Severity distribution" description="Current anomaly severity mix for active time window.">
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={data.severity_distribution} dataKey="count" nameKey="severity" outerRadius={96} />
              <Tooltip contentStyle={{ borderRadius: 12, borderColor: '#e4e4e7', fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </DataPanel>
      </div>

      <DataPanel
        title="Internet feed activity"
        description="Successful source runs publish reference intelligence used for enrichment and scoring."
        badge={<Badge variant="info">{dataSourceStatuses.length} sources</Badge>}
        className="scroll-mt-40"
      >
        {dataSourceStatusQuery.isError && (
          <p className="inline-warning">
            Unable to read connector status. If you see 401 for v2 endpoints, sign out and sign in again to refresh a
            tenant-scoped token.
          </p>
        )}

        {!dataSourceStatusQuery.isError && (
          <div id="sources-section" className="table-wrap scroll-mt-40">
            <table className="data-table">
              <thead className="sticky-table-head">
                <tr>
                  <th scope="col">Source</th>
                  <th scope="col">State</th>
                  <th scope="col">Latest run</th>
                  <th scope="col">Freshness</th>
                  <th scope="col">Failures</th>
                  <th scope="col">Next run</th>
                </tr>
              </thead>
              <tbody>
                {dataSourceStatuses.map((source) => (
                  <tr key={source.source_name} className="interactive-row">
                    <td className="mono">{source.source_name}</td>
                    <td>
                      <Badge
                        variant={sourceStatusBadge(
                          source.enabled,
                          source.latest_status,
                          source.consecutive_failures,
                          source.freshness_seconds,
                          source.freshness_slo_seconds
                        )}
                      >
                        {source.enabled ? source.latest_status ?? 'idle' : 'disabled'}
                      </Badge>
                    </td>
                    <td>{source.last_success_at ? formatDateTime(source.last_success_at, timezone) : 'n/a'}</td>
                    <td>
                      {formatDuration(source.freshness_seconds)}
                      {source.freshness_slo_seconds ? ` / slo ${formatDuration(source.freshness_slo_seconds)}` : ''}
                    </td>
                    <td>{source.consecutive_failures}</td>
                    <td>{source.next_run_at ? formatDateTime(source.next_run_at, timezone) : 'n/a'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DataPanel>

      <DataPanel title="Latest connector runs" badge={<Badge variant="neutral">{dataSourceRuns.length} rows</Badge>}>
        <div className="table-wrap">
          <table className="data-table">
            <thead className="sticky-table-head">
              <tr>
                <th scope="col">Source</th>
                <th scope="col">Status</th>
                <th scope="col">Fetched</th>
                <th scope="col">Upserted</th>
                <th scope="col">Started</th>
                <th scope="col">Finished</th>
              </tr>
            </thead>
            <tbody>
              {dataSourceRuns.map((run) => (
                <tr key={run.run_id} className="interactive-row">
                  <td className="mono">{run.source_name}</td>
                  <td>
                    <Badge
                      variant={
                        run.status === 'failed'
                          ? 'critical'
                          : run.status === 'degraded'
                            ? 'warning'
                            : run.status === 'success' || run.status === 'noop' || run.status === 'partial'
                              ? 'success'
                              : 'info'
                      }
                    >
                      {run.status}
                    </Badge>
                  </td>
                  <td>{run.fetched_records}</td>
                  <td>{run.upserted_records}</td>
                  <td>{formatDateTime(run.started_at, timezone)}</td>
                  <td>{run.finished_at ? formatDateTime(run.finished_at, timezone) : 'running'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </DataPanel>

      <DataPanel
        title="Recent critical alerts"
        badge={<Badge variant="critical">top 10</Badge>}
        className="scroll-mt-40"
      >
        {criticalAlertsQuery.isLoading && <p className="muted">Loading alerts...</p>}

        {!criticalAlertsQuery.isLoading && (
          <div id="critical-alerts-section" className="table-wrap scroll-mt-40">
            <table className="data-table">
              <thead className="sticky-table-head">
                <tr>
                  <th scope="col">Alert</th>
                  <th scope="col">Tenant</th>
                  <th scope="col">Model</th>
                  <th scope="col">Score</th>
                  <th scope="col">Threshold</th>
                  <th scope="col">Created</th>
                </tr>
              </thead>
              <tbody>
                {(criticalAlertsQuery.data?.items ?? []).map((item) => (
                  <tr key={item.alert_id} className="interactive-row">
                    <td className="mono">{item.alert_id}</td>
                    <td>{item.tenant_id}</td>
                    <td className="mono">
                      {item.model_name}:{item.model_version}
                    </td>
                    <td>{item.anomaly_score.toFixed(4)}</td>
                    <td>{item.threshold.toFixed(4)}</td>
                    <td>{formatDateTime(item.created_at, timezone)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DataPanel>
    </DashboardPageFrame>
  );
}
