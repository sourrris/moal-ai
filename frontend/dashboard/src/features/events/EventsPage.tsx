import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { useAuth } from '../../app/state/auth-context';
import { useUI } from '../../app/state/ui-context';
import { fetchEventDetail, fetchEvents } from '../../shared/api/events';
import { formatDateTime } from '../../shared/lib/time';
import { Badge } from '../../shared/ui/badge';
import { Button } from '../../shared/ui/button';
import { Card } from '../../shared/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../../shared/ui/dialog';
import { Input } from '../../shared/ui/input';
import { Select } from '../../shared/ui/select';

const statusVariant: Record<string, 'neutral' | 'info' | 'warning' | 'critical' | 'success'> = {
  queued: 'info',
  processed: 'success',
  anomaly: 'critical',
  failed: 'warning'
};

export function EventsPage() {
  const { token } = useAuth();
  const { tenant, timezone } = useUI();

  const [status, setStatus] = useState('');
  const [source, setSource] = useState('');
  const [eventType, setEventType] = useState('');
  const [eventIdSearch, setEventIdSearch] = useState('');
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [history, setHistory] = useState<string[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);

  const filters = useMemo(
    () => ({
      tenant_id: tenant === 'all' ? undefined : tenant,
      status: status || undefined,
      source: source || undefined,
      event_type: eventType || undefined,
      cursor,
      limit: 20
    }),
    [cursor, eventType, source, status, tenant]
  );

  const eventsQuery = useQuery({
    queryKey: ['events', filters],
    queryFn: async () => fetchEvents(token!, filters),
    enabled: Boolean(token)
  });

  const eventDetailQuery = useQuery({
    queryKey: ['event-detail', selectedEventId],
    queryFn: async () => fetchEventDetail(token!, selectedEventId!),
    enabled: Boolean(token && selectedEventId)
  });

  const rows = (eventsQuery.data?.items ?? []).filter((item) =>
    eventIdSearch ? item.event_id.toLowerCase().includes(eventIdSearch.toLowerCase()) : true
  );

  return (
    <section className="stack-lg">
      <Card>
        <div className="panel-header">
          <h2>Events</h2>
          <span className="muted">Historical ingestion and processing states</span>
        </div>

        <div className="filters-grid">
          <Select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">Status (all)</option>
            <option value="queued">queued</option>
            <option value="processed">processed</option>
            <option value="anomaly">anomaly</option>
            <option value="failed">failed</option>
          </Select>
          <Input value={source} onChange={(event) => setSource(event.target.value)} placeholder="Source" />
          <Input value={eventType} onChange={(event) => setEventType(event.target.value)} placeholder="Event type" />
          <Input value={eventIdSearch} onChange={(event) => setEventIdSearch(event.target.value)} placeholder="Search event_id" />
          <Button
            onClick={() => {
              setCursor(undefined);
              setHistory([]);
            }}
          >
            Apply filters
          </Button>
        </div>

        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Event ID</th>
                <th>Tenant</th>
                <th>Type</th>
                <th>Status</th>
                <th>Source</th>
                <th>Ingested</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => (
                <tr key={item.event_id} className="clickable-row" onClick={() => setSelectedEventId(item.event_id)}>
                  <td className="mono">{item.event_id}</td>
                  <td>{item.tenant_id}</td>
                  <td>{item.event_type}</td>
                  <td>
                    <Badge variant={statusVariant[item.status] ?? 'neutral'}>{item.status}</Badge>
                  </td>
                  <td>{item.source}</td>
                  <td>{formatDateTime(item.ingested_at, timezone)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="pager-row">
          <span className="muted">Total estimate: {eventsQuery.data?.total_estimate ?? 0}</span>
          <div className="pager-actions">
            <Button
              onClick={() => {
                const previous = history[history.length - 1];
                setCursor(previous);
                setHistory((current) => current.slice(0, -1));
              }}
              disabled={history.length === 0}
            >
              Previous
            </Button>
            <Button
              onClick={() => {
                if (!eventsQuery.data?.next_cursor) return;
                setHistory((current) => [...current, cursor ?? '']);
                setCursor(eventsQuery.data.next_cursor ?? undefined);
              }}
              disabled={!eventsQuery.data?.next_cursor}
            >
              Next
            </Button>
          </div>
        </div>
      </Card>

      <Dialog open={Boolean(selectedEventId)} onOpenChange={(open) => !open && setSelectedEventId(null)}>
        <DialogContent>
          <DialogTitle>Event Detail</DialogTitle>
          <DialogDescription>{selectedEventId}</DialogDescription>

          {eventDetailQuery.isLoading && <p className="muted">Loading event detail...</p>}
          {eventDetailQuery.isError && <p className="inline-error">Unable to load event detail.</p>}
          {eventDetailQuery.data && (
            <div className="stack-md">
              <p>
                {eventDetailQuery.data.tenant_id} · {eventDetailQuery.data.event_type} · {eventDetailQuery.data.status}
              </p>
              <p className="mono">Submitted by {eventDetailQuery.data.submitted_by}</p>
              <pre className="json-block">{JSON.stringify(eventDetailQuery.data.payload, null, 2)}</pre>

              <h4>Processing timeline</h4>
              <div className="timeline">
                {eventDetailQuery.data.processing_history.map((item) => (
                  <article key={item.id} className="timeline-item">
                    <p className="mono">
                      {item.model_name}:{item.model_version}
                    </p>
                    <p>
                      score {item.anomaly_score.toFixed(4)} / threshold {item.threshold.toFixed(4)}
                    </p>
                    <p className="muted">{formatDateTime(item.processed_at, timezone)}</p>
                  </article>
                ))}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}
