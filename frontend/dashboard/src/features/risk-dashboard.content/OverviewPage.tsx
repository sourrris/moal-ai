import { useQuery } from '@tanstack/react-query';

import { useAuth } from '../../app/state/auth-context';
import { useUI } from '../../app/state/ui-context';
import { fetchOverviewMetrics } from '../../shared/api/overview';
import { KpiCard } from '../../shared/ui/KpiCard';
import { DashboardPageFrame } from '../../widgets/layout/DashboardPageFrame';

export function OverviewPage() {
  const { token } = useAuth();
  const { window } = useUI();

  const metricsQuery = useQuery({
    queryKey: ['overview-metrics', window],
    queryFn: async () => fetchOverviewMetrics(token!, window),
    enabled: Boolean(token),
    refetchInterval: 15_000,
    refetchIntervalInBackground: true
  });

  if (metricsQuery.isLoading) {
    return <p className="muted">Loading overview metrics...</p>;
  }

  if (metricsQuery.isError || !metricsQuery.data) {
    return <p className="inline-error">Unable to load overview metrics.</p>;
  }

  const data = metricsQuery.data;

  return (
    <DashboardPageFrame>
      <div className="kpi-grid">
        <KpiCard
          label="Total events"
          value={String(data.total_events)}
          meta="behavior events ingested"
        />
        <KpiCard
          label="Total alerts"
          value={String(data.total_alerts)}
          meta="anomalies detected"
        />
        <KpiCard
          label="Open alerts"
          value={String(data.open_alerts)}
          meta="requiring investigation"
          trend={data.open_alerts > 0 ? 'up' : 'neutral'}
        />
        <KpiCard
          label="Avg anomaly score"
          value={data.avg_anomaly_score != null ? data.avg_anomaly_score.toFixed(4) : 'n/a'}
          meta="across scored events"
        />
      </div>
    </DashboardPageFrame>
  );
}
