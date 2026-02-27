import { useQuery } from '@tanstack/react-query';
import { Area, AreaChart, CartesianGrid, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { useAuth } from '../../app/state/auth-context';
import { useLiveAlertState } from '../../app/state/live-alerts-context';
import { useUI } from '../../app/state/ui-context';
import { fetchAlerts } from '../../shared/api/alerts';
import { fetchOverviewMetrics } from '../../shared/api/overview';
import { formatDateTime } from '../../shared/lib/time';
import { Badge } from '../../shared/ui/badge';
import { Card } from '../../shared/ui/card';

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <Card className="metric-tile">
      <span>{label}</span>
      <strong>{value}</strong>
    </Card>
  );
}

export function OverviewPage() {
  const { token } = useAuth();
  const { tenant, window, timezone } = useUI();
  const live = useLiveAlertState();

  const metricsQuery = useQuery({
    queryKey: ['overview-metrics', tenant, window],
    queryFn: async () => fetchOverviewMetrics(token!, tenant, window),
    enabled: Boolean(token)
  });

  const criticalAlertsQuery = useQuery({
    queryKey: ['overview-critical-alerts', tenant, window],
    queryFn: async () =>
      fetchAlerts(token!, {
        tenant_id: tenant === 'all' ? undefined : tenant,
        severity: 'critical',
        limit: 10
      }),
    enabled: Boolean(token)
  });

  if (metricsQuery.isLoading) {
    return <p className="muted">Loading overview metrics...</p>;
  }

  if (metricsQuery.isError || !metricsQuery.data) {
    return <p className="inline-error">Unable to load overview metrics.</p>;
  }

  const data = metricsQuery.data;
  const series = data.timeseries.map((row) => ({
    time: formatDateTime(row.bucket, timezone),
    score: Number((row.avg_score ?? 0).toFixed(4)),
    threshold: Number((row.avg_threshold ?? 0).toFixed(4)),
    volume: row.anomaly_count
  }));

  return (
    <section className="stack-lg">
      <div className="panel-header">
        <h2>Operational Snapshot</h2>
        <Badge variant={live.connected ? (live.stale ? 'warning' : 'success') : 'critical'}>
          {live.connected ? (live.stale ? 'degraded stream' : 'live stream') : 'stream offline'}
        </Badge>
      </div>

      <div className="metrics-grid">
        <MetricTile label="Active anomalies" value={String(data.active_anomalies)} />
        <MetricTile label="Alert rate" value={`${data.alert_rate.toFixed(2)} / hr`} />
        <MetricTile label="Ingestion throughput" value={`${data.ingestion_rate.toFixed(2)} / hr`} />
        <MetricTile label="Model health" value={`${data.model_health.toFixed(1)}%`} />
      </div>

      <div className="grid-two">
        <Card>
          <h3>Anomaly score vs threshold</h3>
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={series}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
              <XAxis dataKey="time" hide />
              <YAxis width={56} />
              <Tooltip />
              <Area type="monotone" dataKey="score" stroke="var(--accent)" fill="rgba(37,99,235,0.18)" />
              <Area type="monotone" dataKey="threshold" stroke="var(--status-warning)" fill="rgba(217,119,6,0.14)" />
            </AreaChart>
          </ResponsiveContainer>
        </Card>

        <Card>
          <h3>Severity distribution</h3>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={data.severity_distribution} dataKey="count" nameKey="severity" outerRadius={96} />
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <Card>
        <div className="panel-header">
          <h3>Recent critical alerts</h3>
          <Badge variant="critical">top 10</Badge>
        </div>

        {criticalAlertsQuery.isLoading && <p className="muted">Loading alerts...</p>}

        {!criticalAlertsQuery.isLoading && (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Alert</th>
                  <th>Tenant</th>
                  <th>Model</th>
                  <th>Score</th>
                  <th>Threshold</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {(criticalAlertsQuery.data?.items ?? []).map((item) => (
                  <tr key={item.alert_id}>
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
      </Card>
    </section>
  );
}
