import { useState } from 'react';

import { useQuery } from '@tanstack/react-query';

import { useAuth } from '../../app/state/auth-context';
import {
  DEFAULT_DASHBOARD_FILTERS,
  type DashboardFilterParams,
  type DashboardTimeWindow,
  fetchDashboardStats,
  fetchRecentDashboardEvents
} from '../../shared/api/overview';
import { Badge } from '../../shared/ui/badge';
import { Button } from '../../shared/ui/button';
import { Card } from '../../shared/ui/card';
import { Input } from '../../shared/ui/input';
import { KpiCard } from '../../shared/ui/KpiCard';
import { Select } from '../../shared/ui/select';
import { DashboardPageFrame } from '../../widgets/layout/DashboardPageFrame';

const REFRESH_INTERVAL = 30_000;
const RECENT_EVENT_LIMIT = 20;
const TIME_WINDOW_OPTIONS: Array<{ value: DashboardTimeWindow; label: string }> = [
  { value: 'all', label: 'All time' },
  { value: '24h', label: 'Last 24 hours' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: 'custom', label: 'Custom range' }
];

const countFormatter = new Intl.NumberFormat();
const compactFormatter = new Intl.NumberFormat(undefined, {
  notation: 'compact',
  maximumFractionDigits: 1
});
const percentFormatter = new Intl.NumberFormat(undefined, {
  style: 'percent',
  maximumFractionDigits: 1
});

function formatCount(value: number) {
  return value >= 1_000 ? compactFormatter.format(value) : countFormatter.format(value);
}

function formatScore(value: number | null) {
  return value == null ? 'n/a' : value.toFixed(4);
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function formatDateTimeShort(value: string) {
  return new Date(value).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function formatHour(hour: number) {
  return `${String(hour).padStart(2, '0')}:00`;
}

function humanizeLabel(value: string) {
  return value.replace(/_/g, ' ');
}

function toBarWidth(count: number, max: number) {
  if (count <= 0 || max <= 0) {
    return '0%';
  }
  return `${Math.max((count / max) * 100, 6)}%`;
}

function toIsoFromLocalInput(value: string) {
  if (!value) {
    return undefined;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return undefined;
  }
  return parsed.toISOString();
}

function describeRange(rangeStart: string | null, rangeEnd: string | null, window: string) {
  if (window === 'all' && !rangeStart && !rangeEnd) {
    return 'All recorded events';
  }
  if (rangeStart && rangeEnd) {
    return `${formatDateTimeShort(rangeStart)} to ${formatDateTimeShort(rangeEnd)}`;
  }
  if (rangeStart) {
    return `From ${formatDateTimeShort(rangeStart)}`;
  }
  if (rangeEnd) {
    return `Until ${formatDateTimeShort(rangeEnd)}`;
  }
  return window;
}

export function OverviewPage() {
  const { token } = useAuth();
  const [draftWindow, setDraftWindow] = useState<DashboardTimeWindow>('all');
  const [draftStartAt, setDraftStartAt] = useState('');
  const [draftEndAt, setDraftEndAt] = useState('');
  const [appliedFilters, setAppliedFilters] = useState<DashboardFilterParams>(DEFAULT_DASHBOARD_FILTERS);

  const statsQuery = useQuery({
    queryKey: ['dashboard-stats', appliedFilters.window, appliedFilters.startAt ?? '', appliedFilters.endAt ?? ''],
    queryFn: async () => fetchDashboardStats(token!, appliedFilters),
    enabled: Boolean(token),
    refetchInterval: REFRESH_INTERVAL,
    refetchIntervalInBackground: true
  });

  const recentEventsQuery = useQuery({
    queryKey: [
      'dashboard-recent-events',
      appliedFilters.window,
      appliedFilters.startAt ?? '',
      appliedFilters.endAt ?? '',
      RECENT_EVENT_LIMIT
    ],
    queryFn: async () => fetchRecentDashboardEvents(token!, appliedFilters, RECENT_EVENT_LIMIT),
    enabled: Boolean(token),
    refetchInterval: REFRESH_INTERVAL,
    refetchIntervalInBackground: true
  });

  if (statsQuery.isLoading) {
    return <p className="muted">Loading dashboard metrics...</p>;
  }

  if (statsQuery.isError || !statsQuery.data) {
    return <p className="inline-error">Unable to load dashboard metrics.</p>;
  }

  const stats = statsQuery.data;
  const recentEvents = recentEventsQuery.data?.items ?? [];
  const maxTypeCount = Math.max(...stats.events_by_type.map((item) => item.count), 1);
  const maxHourCount = Math.max(...stats.events_by_hour.map((item) => item.count), 1);
  const activeRangeLabel = describeRange(stats.range_start, stats.range_end, stats.window);

  function applyFilters() {
    setAppliedFilters({
      window: draftWindow,
      startAt: draftWindow === 'custom' ? toIsoFromLocalInput(draftStartAt) : undefined,
      endAt: draftWindow === 'custom' ? toIsoFromLocalInput(draftEndAt) : undefined
    });
  }

  function resetFilters() {
    setDraftWindow('all');
    setDraftStartAt('');
    setDraftEndAt('');
    setAppliedFilters(DEFAULT_DASHBOARD_FILTERS);
  }

  return (
    <DashboardPageFrame
      eyebrow="Behavior intelligence"
      title="Security behavior in one view."
      subtitle="A near-white analyst surface for event volume, anomaly pressure, geography, user concentration, and recent behavior with all-time visibility by default."
      chips={
        <div className="inline-actions">
          <Badge variant="info">{activeRangeLabel}</Badge>
          <Badge variant="neutral">Updated {formatDateTime(stats.generated_at)}</Badge>
        </div>
      }
    >
      <Card className="dashboard-filter-card">
        <div className="dashboard-filter-copy">
          <div className="panel-copy">
            <span className="panel-kicker">Scope control</span>
            <h2 className="panel-title">Start broad, then narrow to the moment that matters.</h2>
            <p className="panel-summary">
              The board opens on all recorded activity so analysts see the full story first. Tighten it to rolling
              windows or exact timestamps only when the investigation needs sharper focus.
            </p>
          </div>

          <div className="dashboard-note-list">
            <article className="dashboard-note">
              <span className="dashboard-note-label">Current range</span>
              <span className="dashboard-note-value">{activeRangeLabel}</span>
            </article>
            <article className="dashboard-note">
              <span className="dashboard-note-label">Alert pressure</span>
              <span className="dashboard-note-value">
                {formatCount(stats.open_alerts)} open alerts out of {formatCount(stats.total_alerts)} total in scope.
              </span>
            </article>
          </div>
        </div>

        <div className="dashboard-filter-form">
          <div className="panel-copy">
            <span className="panel-kicker">Date and time filters</span>
            <p className="panel-summary">Switch between full history, rolling windows, or an exact investigation interval.</p>
          </div>

          <div className="dashboard-filter-grid">
            <label className="stack-sm">
              <span>Window</span>
              <Select value={draftWindow} onChange={(event) => setDraftWindow(event.target.value as DashboardTimeWindow)}>
                {TIME_WINDOW_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </label>

            {draftWindow === 'custom' && (
              <>
                <label className="stack-sm">
                  <span>Start</span>
                  <Input
                    type="datetime-local"
                    value={draftStartAt}
                    onChange={(event) => setDraftStartAt(event.target.value)}
                  />
                </label>
                <label className="stack-sm">
                  <span>End</span>
                  <Input
                    type="datetime-local"
                    value={draftEndAt}
                    onChange={(event) => setDraftEndAt(event.target.value)}
                  />
                </label>
              </>
            )}
          </div>

          <div className="dashboard-filter-actions">
            <Button variant="warm" onClick={applyFilters}>
              Apply filters
            </Button>
            <Button variant="secondary" onClick={resetFilters}>
              Reset to all time
            </Button>
          </div>
        </div>
      </Card>

      <div className="kpi-grid">
        <KpiCard
          label="Total events"
          value={formatCount(stats.total_events)}
          meta="activity in scope"
        />
        <KpiCard
          label="Total alerts"
          value={formatCount(stats.total_alerts)}
          meta="alerts created"
        />
        <KpiCard
          label="Open alerts"
          value={formatCount(stats.open_alerts)}
          meta="investigation backlog"
          trend={stats.open_alerts > 0 ? 'up' : 'neutral'}
        />
        <KpiCard
          label="Avg anomaly score"
          value={formatScore(stats.avg_anomaly_score)}
          meta="windowed mean"
        />
        <KpiCard
          label="Auth failure rate"
          value={percentFormatter.format(stats.auth_failure_rate)}
          meta="failed attempts / auth requests"
          trend={stats.auth_failure_rate > 0.05 ? 'up' : 'neutral'}
        />
      </div>

      <div className="dashboard-grid">
        <Card className="stack-md">
          <div className="panel-header">
            <div className="panel-copy">
              <span className="panel-kicker">Distribution</span>
              <h2 className="panel-title">Events by type</h2>
              <p className="panel-summary">Which behavior categories dominate the active scope.</p>
            </div>
            <Badge variant="neutral">{formatCount(stats.total_events)} events</Badge>
          </div>

          {stats.events_by_type.length === 0 ? (
            <div className="empty-state">No events available for the selected window.</div>
          ) : (
            <div className="dashboard-distribution">
              {stats.events_by_type.map((item) => (
                <div className="dashboard-distribution-row" key={item.event_type}>
                  <div className="dashboard-distribution-meta">
                    <span className="dashboard-distribution-label">{humanizeLabel(item.event_type)}</span>
                    <span className="dashboard-distribution-value">{formatCount(item.count)}</span>
                  </div>
                  <div className="dashboard-distribution-track">
                    <div
                      className="dashboard-distribution-fill"
                      style={{ width: toBarWidth(item.count, maxTypeCount) }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card className="stack-md">
          <div className="panel-header">
            <div className="panel-copy">
              <span className="panel-kicker">Rhythm</span>
              <h2 className="panel-title">Events by hour</h2>
              <p className="panel-summary">Time-of-day concentration across the selected range.</p>
            </div>
            <Badge variant="neutral">{activeRangeLabel}</Badge>
          </div>

          <div className="dashboard-distribution">
            {stats.events_by_hour.map((item) => (
              <div className="dashboard-distribution-row" key={item.hour}>
                <div className="dashboard-distribution-meta">
                  <span className="dashboard-distribution-label">{formatHour(item.hour)}</span>
                  <span className="dashboard-distribution-value">{formatCount(item.count)}</span>
                </div>
                <div className="dashboard-distribution-track">
                  <div
                    className="dashboard-distribution-fill dashboard-distribution-fill--subtle"
                    style={{ width: toBarWidth(item.count, maxHourCount) }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="stack-md">
          <div className="panel-header">
            <div className="panel-copy">
              <span className="panel-kicker">Identity concentration</span>
              <h2 className="panel-title">Top users</h2>
              <p className="panel-summary">Most active identities with anomaly counts and latest activity.</p>
            </div>
          </div>

          {stats.top_users.length === 0 ? (
            <div className="empty-state">No user activity recorded yet.</div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead className="sticky-table-head">
                  <tr>
                    <th>User</th>
                    <th>Events</th>
                    <th>Anomalies</th>
                    <th>Last seen</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.top_users.map((item) => (
                    <tr className="interactive-row" key={item.user_identifier}>
                      <td className="font-medium text-ink">{item.user_identifier}</td>
                      <td>{formatCount(item.event_count)}</td>
                      <td>
                        <Badge variant={item.anomaly_count > 0 ? 'warning' : 'neutral'}>
                          {formatCount(item.anomaly_count)}
                        </Badge>
                      </td>
                      <td>{formatDateTime(item.last_seen_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card className="stack-md">
          <div className="panel-header">
            <div className="panel-copy">
              <span className="panel-kicker">Geography</span>
              <h2 className="panel-title">Geo distribution</h2>
              <p className="panel-summary">Observed source countries for activity in the current scope.</p>
            </div>
          </div>

          {stats.geo_distribution.length === 0 ? (
            <div className="empty-state">No country data has been ingested yet.</div>
          ) : (
            <div className="dashboard-stat-list">
              {stats.geo_distribution.map((item) => (
                <div className="dashboard-stat-pair" key={item.geo_country}>
                  <span className="dashboard-stat-label">{item.geo_country.toUpperCase()}</span>
                  <span className="dashboard-stat-value">{formatCount(item.count)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card className="stack-md">
        <div className="panel-header">
          <div className="panel-copy">
            <span className="panel-kicker">Live context</span>
            <h2 className="panel-title">Recent events</h2>
            <p className="panel-summary">Latest user activity with source, IP, and anomaly context.</p>
          </div>
          <Badge variant="info">Live refresh</Badge>
        </div>

        {recentEventsQuery.isError ? (
          <p className="inline-error">Unable to load recent events.</p>
        ) : recentEvents.length === 0 ? (
          <div className="empty-state">
            {recentEventsQuery.isLoading ? 'Loading recent events...' : 'No events have been ingested yet.'}
          </div>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead className="sticky-table-head">
                <tr>
                  <th>Time</th>
                  <th>User</th>
                  <th>Type</th>
                  <th>Source</th>
                  <th>IP</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {recentEvents.map((event) => (
                  <tr className="interactive-row" key={event.event_id}>
                    <td>{formatDateTime(event.occurred_at)}</td>
                    <td className="font-medium text-ink">{event.user_identifier}</td>
                    <td>
                      <Badge variant={event.is_anomaly ? 'critical' : 'neutral'}>
                        {humanizeLabel(event.event_type)}
                      </Badge>
                    </td>
                    <td>{event.source}</td>
                    <td>{event.source_ip ?? 'n/a'}</td>
                    <td>
                      <Badge
                        variant={
                          event.is_anomaly
                            ? 'critical'
                            : (event.failed_auth_count > 0 || (event.status_code ?? 0) >= 400)
                              ? 'warning'
                              : 'success'
                        }
                      >
                        {event.is_anomaly
                          ? 'anomaly'
                          : event.failed_auth_count > 0
                            ? 'failed auth'
                            : event.status_code != null
                              ? String(event.status_code)
                              : 'ok'}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </DashboardPageFrame>
  );
}
