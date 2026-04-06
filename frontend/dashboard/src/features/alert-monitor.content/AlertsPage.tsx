import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { useAuth } from '../../app/state/auth-context';
import { useUI } from '../../app/state/ui-context';
import { fetchAlerts, updateAlertStatus } from '../../shared/api/alerts';
import { formatDateTime } from '../../shared/lib/time';
import { Badge } from '../../shared/ui/badge';
import { Button } from '../../shared/ui/button';
import { DataPanel } from '../../shared/ui/DataPanel';
import { Select } from '../../shared/ui/select';
import { DashboardPageFrame } from '../../widgets/layout/DashboardPageFrame';

const severityToVariant: Record<string, 'neutral' | 'warning' | 'critical' | 'success' | 'info'> = {
  critical: 'critical',
  high: 'warning',
  medium: 'info',
  low: 'success'
};

const statusToVariant: Record<string, 'neutral' | 'warning' | 'critical' | 'success' | 'info'> = {
  open: 'critical',
  acknowledged: 'warning',
  resolved: 'success',
  false_positive: 'neutral'
};

export function AlertsPage() {
  const { token } = useAuth();
  const { timezone } = useUI();
  const queryClient = useQueryClient();

  const [severity, setSeverity] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);

  const filters = useMemo(
    () => ({
      severity: severity || undefined,
      status: status || undefined,
      page,
      limit: 20
    }),
    [page, severity, status]
  );

  const alertsQuery = useQuery({
    queryKey: ['alerts', filters],
    queryFn: async () => fetchAlerts(token!, filters),
    enabled: Boolean(token),
    refetchInterval: 15_000,
    refetchIntervalInBackground: true
  });

  const statusMutation = useMutation({
    mutationFn: async ({ alertId, newStatus }: { alertId: string; newStatus: string }) =>
      updateAlertStatus(token!, alertId, newStatus),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      queryClient.invalidateQueries({ queryKey: ['overview-metrics'] });
    }
  });

  const rows = alertsQuery.data?.items ?? [];
  const activeFilterCount = [severity, status].filter(Boolean).length;

  return (
    <DashboardPageFrame
      chips={
        <div className="inline-actions">
          <Badge variant="info">total {alertsQuery.data?.total ?? 0}</Badge>
          <Badge variant="neutral">filters {activeFilterCount}</Badge>
        </div>
      }
    >
      <DataPanel
        title="Alert registry"
        description="Anomaly alerts with lifecycle management."
        actions={
          <Button
            variant="secondary"
            onClick={() => { setSeverity(''); setStatus(''); setPage(1); }}
            disabled={activeFilterCount === 0}
          >
            Clear filters
          </Button>
        }
      >
        <div className="table-toolbar">
          <Select value={severity} onChange={(event) => { setSeverity(event.target.value); setPage(1); }}>
            <option value="">Severity (all)</option>
            <option value="critical">critical</option>
            <option value="high">high</option>
            <option value="medium">medium</option>
            <option value="low">low</option>
          </Select>
          <Select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
            <option value="">Status (all)</option>
            <option value="open">open</option>
            <option value="acknowledged">acknowledged</option>
            <option value="resolved">resolved</option>
            <option value="false_positive">false positive</option>
          </Select>
        </div>

        {alertsQuery.isLoading && <p className="muted">Loading alerts...</p>}
        {alertsQuery.isError && <p className="inline-error">Unable to load alerts.</p>}

        {alertsQuery.data && (
          <>
            <div className="table-wrap">
              <table className="data-table">
                <thead className="sticky-table-head">
                  <tr>
                    <th scope="col">User</th>
                    <th scope="col">Severity</th>
                    <th scope="col">Score</th>
                    <th scope="col">Threshold</th>
                    <th scope="col">Status</th>
                    <th scope="col">Created</th>
                    <th scope="col">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((item) => (
                    <tr key={item.alert_id} className="interactive-row">
                      <td className="mono">{item.user_identifier}</td>
                      <td>
                        <Badge variant={severityToVariant[item.severity] ?? 'neutral'}>{item.severity}</Badge>
                      </td>
                      <td>{item.anomaly_score.toFixed(4)}</td>
                      <td>{item.threshold.toFixed(4)}</td>
                      <td>
                        <Badge variant={statusToVariant[item.status] ?? 'neutral'}>{item.status}</Badge>
                      </td>
                      <td>{formatDateTime(item.created_at, timezone)}</td>
                      <td>
                        <div className="inline-actions">
                          {item.status === 'open' && (
                            <Button
                              variant="secondary"
                              onClick={() => statusMutation.mutate({ alertId: item.alert_id, newStatus: 'acknowledged' })}
                              disabled={statusMutation.isPending}
                            >
                              Ack
                            </Button>
                          )}
                          {(item.status === 'open' || item.status === 'acknowledged') && (
                            <Button
                              variant="secondary"
                              onClick={() => statusMutation.mutate({ alertId: item.alert_id, newStatus: 'resolved' })}
                              disabled={statusMutation.isPending}
                            >
                              Resolve
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                  {rows.length === 0 && (
                    <tr>
                      <td colSpan={7} className="muted">No alerts match current filters.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="pager-row">
              <span className="muted">
                Page {alertsQuery.data.page} of {alertsQuery.data.total_pages}. Total: {alertsQuery.data.total}
              </span>
              <div className="pager-actions">
                <Button onClick={() => setPage((c) => Math.max(1, c - 1))} disabled={alertsQuery.data.page <= 1}>
                  Previous
                </Button>
                <Button onClick={() => setPage((c) => c + 1)} disabled={alertsQuery.data.page >= alertsQuery.data.total_pages}>
                  Next
                </Button>
              </div>
            </div>
          </>
        )}
      </DataPanel>
    </DashboardPageFrame>
  );
}
