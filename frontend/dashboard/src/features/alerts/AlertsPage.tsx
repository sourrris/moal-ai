import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { useAuth } from '../../app/state/auth-context';
import { useLiveAlertState } from '../../app/state/live-alerts-context';
import { useUI } from '../../app/state/ui-context';
import { fetchAlertDetail, fetchAlerts } from '../../shared/api/alerts';
import { formatDateTime } from '../../shared/lib/time';
import { Badge } from '../../shared/ui/badge';
import { Button } from '../../shared/ui/button';
import { DataPanel } from '../../shared/ui/DataPanel';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../../shared/ui/dialog';
import { Input } from '../../shared/ui/input';
import { Select } from '../../shared/ui/select';
import { DashboardPageFrame } from '../../widgets/layout/DashboardPageFrame';

type SortKey = 'severity' | 'score' | 'created';
type SortDirection = 'asc' | 'desc';

const severityToVariant: Record<string, 'neutral' | 'warning' | 'critical' | 'success' | 'info'> = {
  critical: 'critical',
  high: 'warning',
  medium: 'info',
  low: 'success'
};

const severitySortRank: Record<string, number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1
};

function sortMarker(key: SortKey, activeKey: SortKey, direction: SortDirection) {
  if (key !== activeKey) {
    return ' ↕';
  }
  return direction === 'asc' ? ' ↑' : ' ↓';
}

export function AlertsPage() {
  const { token } = useAuth();
  const { tenant, timezone } = useUI();
  const live = useLiveAlertState();

  const [severity, setSeverity] = useState('');
  const [modelVersion, setModelVersion] = useState('');
  const [scoreMin, setScoreMin] = useState('');
  const [scoreMax, setScoreMax] = useState('');
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [cursorHistory, setCursorHistory] = useState<string[]>([]);
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>('created');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');

  const filters = useMemo(
    () => ({
      tenant_id: tenant === 'all' ? undefined : tenant,
      severity: severity || undefined,
      model_version: modelVersion || undefined,
      score_min: scoreMin ? Number(scoreMin) : undefined,
      score_max: scoreMax ? Number(scoreMax) : undefined,
      cursor,
      limit: 20
    }),
    [cursor, modelVersion, scoreMax, scoreMin, severity, tenant]
  );

  const alertsQuery = useQuery({
    queryKey: ['alerts', filters],
    queryFn: async () => fetchAlerts(token!, filters),
    enabled: Boolean(token),
    refetchInterval: live.connected && !live.stale ? false : 15_000,
    refetchIntervalInBackground: true
  });

  const alertDetailQuery = useQuery({
    queryKey: ['alert-detail', selectedAlertId],
    queryFn: async () => fetchAlertDetail(token!, selectedAlertId!),
    enabled: Boolean(token && selectedAlertId)
  });

  const activeFilterCount = [severity, modelVersion, scoreMin, scoreMax].filter(Boolean).length;

  const sortedAlerts = useMemo(() => {
    const list = [...(alertsQuery.data?.items ?? [])];

    list.sort((left, right) => {
      let result = 0;
      if (sortKey === 'severity') {
        result = (severitySortRank[left.severity] ?? 0) - (severitySortRank[right.severity] ?? 0);
      } else if (sortKey === 'score') {
        result = left.anomaly_score - right.anomaly_score;
      } else {
        result = Date.parse(left.created_at) - Date.parse(right.created_at);
      }

      return sortDirection === 'asc' ? result : -result;
    });

    return list;
  }, [alertsQuery.data?.items, sortDirection, sortKey]);

  const toggleSort = (nextKey: SortKey) => {
    setSortDirection((currentDirection) => {
      if (sortKey !== nextKey) {
        return 'desc';
      }
      return currentDirection === 'asc' ? 'desc' : 'asc';
    });
    setSortKey(nextKey);
  };

  return (
    <DashboardPageFrame
      chips={
        <div className="inline-actions">
          <Badge variant={live.connected ? 'success' : 'critical'}>{live.connected ? 'live' : 'offline'}</Badge>
          <Badge variant="neutral">filters {activeFilterCount}</Badge>
          <Badge variant="info">total {alertsQuery.data?.total_estimate ?? 0}</Badge>
        </div>
      }
    >
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(320px,0.8fr)]">
        <DataPanel
          title="Alert registry"
          description="Sortable list of anomalies with model and tenant context."
          actions={
            <Button
              variant="secondary"
              onClick={() => {
                setSeverity('');
                setModelVersion('');
                setScoreMin('');
                setScoreMax('');
                setCursor(undefined);
                setCursorHistory([]);
              }}
              disabled={activeFilterCount === 0}
            >
              Clear filters
            </Button>
          }
        >
          <div className="table-toolbar">
            <Select value={severity} onChange={(event) => setSeverity(event.target.value)}>
              <option value="">Severity (all)</option>
              <option value="critical">critical</option>
              <option value="high">high</option>
              <option value="medium">medium</option>
            </Select>

            <Input value={modelVersion} onChange={(event) => setModelVersion(event.target.value)} placeholder="Model version" />
            <Input value={scoreMin} onChange={(event) => setScoreMin(event.target.value)} placeholder="Score min" type="number" />
            <Input value={scoreMax} onChange={(event) => setScoreMax(event.target.value)} placeholder="Score max" type="number" />

            <Button
              onClick={() => {
                setCursor(undefined);
                setCursorHistory([]);
              }}
            >
              Apply filters
            </Button>
          </div>

          {alertsQuery.isLoading && <p className="muted">Loading alerts...</p>}
          {alertsQuery.isError && <p className="inline-error">Unable to load alerts.</p>}

          {alertsQuery.data && (
            <>
              <div className="table-wrap">
                <table className="data-table">
                  <thead className="sticky-table-head">
                    <tr>
                      <th scope="col">Alert</th>
                      <th scope="col">
                        <button type="button" className="interactive-surface rounded px-1" onClick={() => toggleSort('severity')}>
                          Severity{sortMarker('severity', sortKey, sortDirection)}
                        </button>
                      </th>
                      <th scope="col">Tenant</th>
                      <th scope="col">Model</th>
                      <th scope="col">
                        <button type="button" className="interactive-surface rounded px-1" onClick={() => toggleSort('score')}>
                          Score{sortMarker('score', sortKey, sortDirection)}
                        </button>
                      </th>
                      <th scope="col">Threshold</th>
                      <th scope="col">
                        <button type="button" className="interactive-surface rounded px-1" onClick={() => toggleSort('created')}>
                          Created{sortMarker('created', sortKey, sortDirection)}
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedAlerts.map((item) => (
                      <tr
                        key={item.alert_id}
                        onClick={() => setSelectedAlertId(item.alert_id)}
                        className="clickable-row interactive-row"
                      >
                        <td className="mono">{item.alert_id}</td>
                        <td>
                          <Badge variant={severityToVariant[item.severity] ?? 'neutral'}>{item.severity}</Badge>
                        </td>
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

              <div className="pager-row">
                <span className="muted">Total estimate: {alertsQuery.data.total_estimate}</span>
                <div className="pager-actions">
                  <Button
                    onClick={() => {
                      const previous = cursorHistory[cursorHistory.length - 1];
                      setCursor(previous);
                      setCursorHistory((history) => history.slice(0, -1));
                    }}
                    disabled={cursorHistory.length === 0}
                  >
                    Previous
                  </Button>

                  <Button
                    onClick={() => {
                      if (!alertsQuery.data?.next_cursor) return;
                      setCursorHistory((history) => [...history, cursor ?? '']);
                      setCursor(alertsQuery.data.next_cursor ?? undefined);
                    }}
                    disabled={!alertsQuery.data.next_cursor}
                  >
                    Next
                  </Button>
                </div>
              </div>
            </>
          )}
        </DataPanel>

        <DataPanel
          title="Live stream"
          description="Newest websocket alerts with real-time score movement."
          badge={<Badge variant={live.connected ? 'success' : 'critical'}>{live.connected ? 'socket live' : 'socket offline'}</Badge>}
        >
          <div className="live-list">
            {live.alerts.slice(0, 10).map((alert) => (
              <article className="live-row interactive-surface" key={alert.alert_id}>
                <div>
                  <strong>{alert.tenant_id}</strong>
                  <p className="muted mono">
                    {alert.model_name}:{alert.model_version}
                  </p>
                </div>
                <div>
                  <p>{alert.anomaly_score.toFixed(4)}</p>
                  <p className="muted">{formatDateTime(alert.created_at, timezone)}</p>
                </div>
              </article>
            ))}
            {live.alerts.length === 0 && <p className="muted">No live alerts in the current session.</p>}
          </div>
        </DataPanel>
      </div>

      <Dialog open={Boolean(selectedAlertId)} onOpenChange={(open) => !open && setSelectedAlertId(null)}>
        <DialogContent>
          <DialogTitle>Alert Detail</DialogTitle>
          <DialogDescription>{selectedAlertId}</DialogDescription>

          {alertDetailQuery.isLoading && <p className="muted">Loading alert detail...</p>}
          {alertDetailQuery.isError && <p className="inline-error">Unable to load alert detail.</p>}
          {alertDetailQuery.data && (
            <div className="stack-md">
              <div className="grid grid-cols-1 gap-2 rounded-2xl border border-stroke bg-zinc-50 p-3 text-sm sm:grid-cols-2">
                <p>
                  Severity <strong>{alertDetailQuery.data.severity}</strong>
                </p>
                <p>
                  Tenant <strong>{alertDetailQuery.data.tenant_id}</strong>
                </p>
                <p className="mono">
                  Model {alertDetailQuery.data.model_name}:{alertDetailQuery.data.model_version}
                </p>
                <p>
                  Score {alertDetailQuery.data.anomaly_score.toFixed(4)} / {alertDetailQuery.data.threshold.toFixed(4)}
                </p>
              </div>
              <pre className="json-block">{JSON.stringify(alertDetailQuery.data.event_payload ?? {}, null, 2)}</pre>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </DashboardPageFrame>
  );
}
