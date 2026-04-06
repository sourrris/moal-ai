import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { useAuth } from '../../app/state/auth-context';
import { useUI } from '../../app/state/ui-context';
import { fetchEvents } from '../../shared/api/events';
import { formatDateTime } from '../../shared/lib/time';
import { Badge } from '../../shared/ui/badge';
import { Button } from '../../shared/ui/button';
import { DataPanel } from '../../shared/ui/DataPanel';
import { Input } from '../../shared/ui/input';
import { Select } from '../../shared/ui/select';
import { DashboardPageFrame } from '../../widgets/layout/DashboardPageFrame';

const statusVariant: Record<string, 'neutral' | 'info' | 'warning' | 'critical' | 'success'> = {
  normal: 'success',
  anomaly: 'critical'
};

export function EventsPage() {
  const { token } = useAuth();
  const { timezone } = useUI();

  const [eventType, setEventType] = useState('');
  const [source, setSource] = useState('');
  const [userSearch, setUserSearch] = useState('');
  const [anomalyOnly, setAnomalyOnly] = useState(false);
  const [page, setPage] = useState(1);

  const filters = useMemo(
    () => ({
      event_type: eventType || undefined,
      source: source || undefined,
      user_identifier: userSearch || undefined,
      is_anomaly: anomalyOnly ? true : undefined,
      page,
      limit: 20
    }),
    [anomalyOnly, eventType, page, source, userSearch]
  );

  const eventsQuery = useQuery({
    queryKey: ['events', filters],
    queryFn: async () => fetchEvents(token!, filters),
    enabled: Boolean(token),
    refetchInterval: 15_000,
    refetchIntervalInBackground: true
  });

  const rows = eventsQuery.data?.items ?? [];
  const activeFilterCount = [eventType, source, userSearch, anomalyOnly ? 'y' : ''].filter(Boolean).length;

  return (
    <DashboardPageFrame
      chips={
        <div className="inline-actions">
          <Badge variant="info">events {eventsQuery.data?.total ?? 0}</Badge>
          <Badge variant="neutral">
            page {eventsQuery.data?.page ?? page}/{eventsQuery.data?.total_pages ?? 1}
          </Badge>
        </div>
      }
    >
      <DataPanel
        title="Behavior events"
        description="User behavior events with anomaly scores from the ML pipeline."
        actions={
          <Button
            variant="secondary"
            onClick={() => {
              setEventType('');
              setSource('');
              setUserSearch('');
              setAnomalyOnly(false);
              setPage(1);
            }}
            disabled={activeFilterCount === 0 && page === 1}
          >
            Clear filters
          </Button>
        }
      >
        <div className="table-toolbar">
          <Input
            aria-label="User search"
            value={userSearch}
            onChange={(event) => { setUserSearch(event.target.value); setPage(1); }}
            placeholder="User identifier"
          />
          <Input
            aria-label="Event type filter"
            value={eventType}
            onChange={(event) => { setEventType(event.target.value); setPage(1); }}
            placeholder="Event type"
          />
          <Input
            aria-label="Source filter"
            value={source}
            onChange={(event) => { setSource(event.target.value); setPage(1); }}
            placeholder="Source"
          />
          <Select
            aria-label="Anomaly filter"
            value={anomalyOnly ? 'anomaly' : ''}
            onChange={(event) => { setAnomalyOnly(event.target.value === 'anomaly'); setPage(1); }}
          >
            <option value="">All events</option>
            <option value="anomaly">Anomalies only</option>
          </Select>
        </div>

        <div className="table-wrap">
          <table className="data-table">
            <thead className="sticky-table-head">
              <tr>
                <th scope="col">User</th>
                <th scope="col">Type</th>
                <th scope="col">Source</th>
                <th scope="col">IP</th>
                <th scope="col">Country</th>
                <th scope="col">Score</th>
                <th scope="col">Anomaly</th>
                <th scope="col">Occurred</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => (
                <tr key={item.event_id} className="interactive-row">
                  <td className="mono">{item.user_identifier}</td>
                  <td>{item.event_type}</td>
                  <td>{item.source}</td>
                  <td className="mono">{item.source_ip ?? 'n/a'}</td>
                  <td>{item.geo_country ?? 'n/a'}</td>
                  <td>{item.anomaly_score != null ? item.anomaly_score.toFixed(4) : 'n/a'}</td>
                  <td>
                    <Badge variant={item.is_anomaly ? statusVariant.anomaly : statusVariant.normal}>
                      {item.is_anomaly ? 'anomaly' : 'normal'}
                    </Badge>
                  </td>
                  <td>{formatDateTime(item.occurred_at, timezone)}</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={8} className="muted">
                    No events match current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="pager-row">
          <span className="muted">
            Page {eventsQuery.data?.page ?? page} of {eventsQuery.data?.total_pages ?? 1}. Total: {eventsQuery.data?.total ?? 0}
          </span>
          <div className="pager-actions">
            <Button onClick={() => setPage((c) => Math.max(1, c - 1))} disabled={(eventsQuery.data?.page ?? page) <= 1}>
              Previous
            </Button>
            <Button onClick={() => setPage((c) => c + 1)} disabled={(eventsQuery.data?.page ?? page) >= (eventsQuery.data?.total_pages ?? 1)}>
              Next
            </Button>
          </div>
        </div>
      </DataPanel>
    </DashboardPageFrame>
  );
}
