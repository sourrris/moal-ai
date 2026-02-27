import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { useAuth } from '../../app/state/auth-context';
import { useLiveAlertState } from '../../app/state/live-alerts-context';
import { useUI } from '../../app/state/ui-context';
import { fetchAlertDetail, fetchAlerts } from '../../shared/api/alerts';
import { formatDateTime } from '../../shared/lib/time';
import { Badge } from '../../shared/ui/badge';
import { Button } from '../../shared/ui/button';
import { Card } from '../../shared/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../../shared/ui/dialog';
import { Input } from '../../shared/ui/input';
import { Select } from '../../shared/ui/select';

const severityToVariant: Record<string, 'neutral' | 'warning' | 'critical' | 'success' | 'info'> = {
  critical: 'critical',
  high: 'warning',
  medium: 'info',
  low: 'success'
};

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
    enabled: Boolean(token)
  });

  const alertDetailQuery = useQuery({
    queryKey: ['alert-detail', selectedAlertId],
    queryFn: async () => fetchAlertDetail(token!, selectedAlertId!),
    enabled: Boolean(token && selectedAlertId)
  });

  return (
    <section className="stack-lg">
      <Card>
        <div className="panel-header">
          <h2>Alerts</h2>
          <Badge variant={live.connected ? 'success' : 'critical'}>{live.connected ? 'live' : 'offline'}</Badge>
        </div>

        <div className="filters-grid">
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
                <thead>
                  <tr>
                    <th>Alert</th>
                    <th>Severity</th>
                    <th>Tenant</th>
                    <th>Model</th>
                    <th>Score</th>
                    <th>Threshold</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {alertsQuery.data.items.map((item) => (
                    <tr key={item.alert_id} onClick={() => setSelectedAlertId(item.alert_id)} className="clickable-row">
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
      </Card>

      <Card>
        <div className="panel-header">
          <h3>Live Stream</h3>
          <span className="muted">Newest websocket alerts</span>
        </div>

        <div className="live-list">
          {live.alerts.slice(0, 8).map((alert) => (
            <article className="live-row" key={alert.alert_id}>
              <div>
                <strong>{alert.tenant_id}</strong>
                <p className="muted mono">{alert.model_name}:{alert.model_version}</p>
              </div>
              <div>
                <p>{alert.anomaly_score.toFixed(4)}</p>
                <p className="muted">{formatDateTime(alert.created_at, timezone)}</p>
              </div>
            </article>
          ))}
        </div>
      </Card>

      <Dialog open={Boolean(selectedAlertId)} onOpenChange={(open) => !open && setSelectedAlertId(null)}>
        <DialogContent>
          <DialogTitle>Alert Detail</DialogTitle>
          <DialogDescription>{selectedAlertId}</DialogDescription>

          {alertDetailQuery.isLoading && <p className="muted">Loading alert detail...</p>}
          {alertDetailQuery.isError && <p className="inline-error">Unable to load alert detail.</p>}
          {alertDetailQuery.data && (
            <div className="stack-md">
              <p>
                Severity <strong>{alertDetailQuery.data.severity}</strong> for tenant{' '}
                <strong>{alertDetailQuery.data.tenant_id}</strong>
              </p>
              <p className="mono">
                model {alertDetailQuery.data.model_name}:{alertDetailQuery.data.model_version}
              </p>
              <p>
                Score {alertDetailQuery.data.anomaly_score.toFixed(4)} vs threshold{' '}
                {alertDetailQuery.data.threshold.toFixed(4)}
              </p>
              <pre className="json-block">{JSON.stringify(alertDetailQuery.data.event_payload ?? {}, null, 2)}</pre>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}
