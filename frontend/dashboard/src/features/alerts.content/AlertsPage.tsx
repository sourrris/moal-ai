import { useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';

import { useAuth } from '../../app/state/auth-context';
import {
  acknowledgeAlert,
  type Alert,
  fetchAlerts,
  markFalsePositive,
  resolveAlert
} from '../../shared/api/alerts';
import { Badge } from '../../shared/ui/badge';
import { Button } from '../../shared/ui/button';
import { Card } from '../../shared/ui/card';
import { Select } from '../../shared/ui/select';
import { DashboardPageFrame } from '../../widgets/layout/DashboardPageFrame';

const REFRESH_INTERVAL = 15_000;
const PAGE_SIZE = 25;

const STATE_OPTIONS = [
  { value: '', label: 'All states' },
  { value: 'open', label: 'Open' },
  { value: 'acknowledged', label: 'Acknowledged' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'false_positive', label: 'False positive' }
];

const severityVariant: Record<string, 'critical' | 'warning' | 'neutral'> = {
  critical: 'critical',
  high: 'warning'
};

const stateVariant: Record<string, 'critical' | 'warning' | 'success' | 'neutral' | 'info'> = {
  open: 'critical',
  acknowledged: 'warning',
  resolved: 'success',
  false_positive: 'neutral'
};

function formatDateTime(value: string) {
  return new Date(value).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function AlertActions({ alert, token }: { alert: Alert; token: string }) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState('');
  const [expanded, setExpanded] = useState(false);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['alerts'] });

  const ackMutation = useMutation({
    mutationFn: () => acknowledgeAlert(token, alert.alert_id, note || undefined),
    onSuccess: invalidate
  });

  const resolveMutation = useMutation({
    mutationFn: () => resolveAlert(token, alert.alert_id, note || undefined),
    onSuccess: invalidate
  });

  const fpMutation = useMutation({
    mutationFn: () => markFalsePositive(token, alert.alert_id, note || undefined),
    onSuccess: invalidate
  });

  const isLoading = ackMutation.isPending || resolveMutation.isPending || fpMutation.isPending;

  if (alert.state === 'resolved' || alert.state === 'false_positive') {
    return alert.note ? (
      <p className="text-[0.88rem] text-ink-muted italic">{alert.note}</p>
    ) : null;
  }

  return (
    <div className="grid gap-2">
      {expanded && (
        <textarea
          className="ui-input h-20 resize-none text-[0.88rem]"
          placeholder="Add a note (optional)..."
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={2000}
        />
      )}
      <div className="inline-actions">
        {!expanded && (
          <Button variant="secondary" onClick={() => setExpanded(true)} disabled={isLoading}>
            Actions
          </Button>
        )}
        {expanded && (
          <>
            {alert.state === 'open' && (
              <Button variant="warm" onClick={() => ackMutation.mutate()} disabled={isLoading}>
                Acknowledge
              </Button>
            )}
            <Button variant="secondary" onClick={() => resolveMutation.mutate()} disabled={isLoading}>
              Resolve
            </Button>
            <Button variant="ghost" onClick={() => fpMutation.mutate()} disabled={isLoading}>
              False positive
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

export function AlertsPage() {
  const { token } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const stateFilter = searchParams.get('state') ?? '';
  const [offset, setOffset] = useState(0);

  const alertsQuery = useQuery({
    queryKey: ['alerts', stateFilter, offset],
    queryFn: async () => fetchAlerts(token!, stateFilter || undefined, PAGE_SIZE, offset),
    enabled: Boolean(token),
    refetchInterval: REFRESH_INTERVAL
  });

  const alerts = alertsQuery.data ?? [];

  return (
    <DashboardPageFrame
      eyebrow="Investigation"
      title="Alerts"
      subtitle="Anomalous events that exceeded the model threshold. Review, acknowledge, resolve, or mark as false positive."
      chips={
        <Badge variant="info">{alerts.length} alerts loaded</Badge>
      }
    >
      <Card className="stack-md">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="panel-copy">
            <span className="panel-kicker">Filter</span>
          </div>
          <div className="flex items-center gap-3">
            <Select
              value={stateFilter}
              onChange={(e) => {
                setOffset(0);
                const val = e.target.value;
                setSearchParams(val ? { state: val } : {});
              }}
            >
              {STATE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </Select>
          </div>
        </div>
      </Card>

      {alertsQuery.isLoading ? (
        <p className="muted">Loading alerts...</p>
      ) : alertsQuery.isError ? (
        <p className="inline-error">Unable to load alerts.</p>
      ) : alerts.length === 0 ? (
        <div className="empty-state">No alerts match the current filter.</div>
      ) : (
        <div className="grid gap-4">
          {alerts.map((alert) => (
            <Card key={alert.alert_id} className="grid gap-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="grid gap-1">
                  <div className="inline-actions">
                    <Badge variant={severityVariant[alert.severity] ?? 'neutral'}>
                      {alert.severity}
                    </Badge>
                    <Badge variant={stateVariant[alert.state] ?? 'neutral'}>
                      {alert.state.replace(/_/g, ' ')}
                    </Badge>
                  </div>
                  <p className="text-[1.1rem] font-medium text-ink">{alert.user_identifier}</p>
                  <p className="text-[0.88rem] text-ink-muted">
                    Score <span className="font-medium text-ink">{alert.anomaly_score.toFixed(4)}</span>
                    {' '} / threshold {alert.threshold.toFixed(4)}
                    {' '} &middot; {alert.model_name} v{alert.model_version}
                  </p>
                </div>
                <div className="text-right text-[0.82rem] text-ink-soft">
                  <p>{formatDateTime(alert.created_at)}</p>
                  {alert.updated_at !== alert.created_at && (
                    <p>Updated {formatDateTime(alert.updated_at)}</p>
                  )}
                </div>
              </div>

              <AlertActions alert={alert} token={token!} />
            </Card>
          ))}

          <div className="pager-row">
            <span className="text-[0.88rem] text-ink-muted">
              Showing {offset + 1}&ndash;{offset + alerts.length}
            </span>
            <div className="pager-actions">
              <Button variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                Previous
              </Button>
              <Button variant="secondary" disabled={alerts.length < PAGE_SIZE} onClick={() => setOffset(offset + PAGE_SIZE)}>
                Next
              </Button>
            </div>
          </div>
        </div>
      )}
    </DashboardPageFrame>
  );
}
