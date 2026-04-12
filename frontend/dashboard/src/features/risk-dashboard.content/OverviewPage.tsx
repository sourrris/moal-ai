import { useState } from 'react';

import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  Treemap,
  XAxis,
  YAxis
} from 'recharts';

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
const CHART_EVENT_LIMIT = 100;
const TIME_WINDOW_OPTIONS: Array<{ value: DashboardTimeWindow; label: string }> = [
  { value: 'all', label: 'All time' },
  { value: '24h', label: 'Last 24 hours' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: 'custom', label: 'Custom range' }
];

const CHART_COLORS = {
  ink: '#000000',
  inkMuted: '#4e4e4e',
  inkSoft: '#777169',
  critical: '#9c4139',
  warning: '#8a6539',
  success: '#2f7f56',
  canvasWarm: '#f5f2ef',
  grid: '#e5e5e5',
  surface: '#ffffff'
};

const TYPE_PALETTE = ['#000000', '#4e4e4e', '#777169', '#8a6539', '#5f7489', '#9c4139', '#2f7f56', '#a08872'];

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

function ChartTooltipContent({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number; name: string; color?: string }>; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-panel border border-black/5 bg-white px-3 py-2 text-[0.82rem] shadow-outline">
      {label && <p className="mb-1 text-ink-soft">{label}</p>}
      {payload.map((entry, i) => (
        <p key={i} className="text-ink">
          <span className="font-medium">{entry.name}:</span> {typeof entry.value === 'number' ? entry.value.toLocaleString() : entry.value}
        </p>
      ))}
    </div>
  );
}

export function OverviewPage() {
  const { token } = useAuth();
  const navigate = useNavigate();
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

  const chartEventsQuery = useQuery({
    queryKey: [
      'dashboard-chart-events',
      appliedFilters.window,
      appliedFilters.startAt ?? '',
      appliedFilters.endAt ?? '',
      CHART_EVENT_LIMIT
    ],
    queryFn: async () => fetchRecentDashboardEvents(token!, appliedFilters, CHART_EVENT_LIMIT),
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
  const chartEvents = chartEventsQuery.data?.items ?? [];
  const activeRangeLabel = describeRange(stats.range_start, stats.range_end, stats.window);

  // Prepare anomaly timeline data from chart events (sorted chronologically)
  const anomalyTimeline = [...chartEvents]
    .filter((e) => e.anomaly_score != null)
    .sort((a, b) => new Date(a.occurred_at).getTime() - new Date(b.occurred_at).getTime())
    .map((e) => ({
      time: new Date(e.occurred_at).getTime(),
      label: formatDateTimeShort(e.occurred_at),
      score: e.anomaly_score ?? 0,
      user: e.user_identifier,
      isAnomaly: e.is_anomaly ?? false
    }));

  // Compute threshold from the stats avg + some heuristic, or use a fixed reference
  const avgScore = stats.avg_anomaly_score ?? 0;
  const thresholdLine = avgScore > 0 ? avgScore * 3 : 0.5;

  // Events by hour with full 24-hour coverage
  const hourData = Array.from({ length: 24 }, (_, i) => {
    const match = stats.events_by_hour.find((h) => h.hour === i);
    return { hour: formatHour(i), count: match?.count ?? 0, hourNum: i };
  });

  // Geo treemap data
  const geoTreemap = stats.geo_distribution.map((g) => ({
    name: g.geo_country.toUpperCase(),
    size: g.count,
    count: g.count
  }));

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
      subtitle="Event volume, anomaly pressure, geography, user concentration, and recent behavior with all-time visibility by default."
      chips={
        <div className="inline-actions">
          <Badge variant="info">{activeRangeLabel}</Badge>
          <Badge variant="neutral">Updated {formatDateTime(stats.generated_at)}</Badge>
        </div>
      }
    >
      {/* Scope control / filters */}
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

      {/* KPI cards */}
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
          onClick={() => navigate('/alerts')}
        />
        <KpiCard
          label="Open alerts"
          value={formatCount(stats.open_alerts)}
          meta="investigation backlog"
          trend={stats.open_alerts > 0 ? 'up' : 'neutral'}
          onClick={() => navigate('/alerts?state=open')}
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

      {/* Anomaly score timeline */}
      {anomalyTimeline.length > 0 && (
        <Card className="stack-md">
          <div className="panel-header">
            <div className="panel-copy">
              <span className="panel-kicker">Signal</span>
              <h2 className="panel-title">Anomaly score timeline</h2>
              <p className="panel-summary">Reconstruction error over time. Points above the threshold line triggered alerts.</p>
            </div>
            <Badge variant={anomalyTimeline.some((p) => p.isAnomaly) ? 'critical' : 'neutral'}>
              {anomalyTimeline.filter((p) => p.isAnomaly).length} anomalies
            </Badge>
          </div>

          <div style={{ width: '100%', height: 280 }}>
            <ResponsiveContainer>
              <ScatterChart margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />
                <XAxis
                  dataKey="time"
                  type="number"
                  domain={['dataMin', 'dataMax']}
                  tickFormatter={(t: number) => new Date(t).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                  tick={{ fontSize: 11, fill: CHART_COLORS.inkSoft }}
                  stroke={CHART_COLORS.grid}
                />
                <YAxis
                  dataKey="score"
                  tick={{ fontSize: 11, fill: CHART_COLORS.inkSoft }}
                  stroke={CHART_COLORS.grid}
                  tickFormatter={(v: number) => v.toFixed(2)}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const d = payload[0].payload;
                    return (
                      <div className="rounded-panel border border-black/5 bg-white px-3 py-2 text-[0.82rem] shadow-outline">
                        <p className="text-ink-soft">{d.label}</p>
                        <p className="font-medium text-ink">Score: {d.score.toFixed(4)}</p>
                        <p className="text-ink-muted">User: {d.user}</p>
                        {d.isAnomaly && <p className="text-critical font-medium">Anomaly detected</p>}
                      </div>
                    );
                  }}
                />
                <ReferenceLine
                  y={thresholdLine}
                  stroke={CHART_COLORS.critical}
                  strokeDasharray="6 4"
                  strokeWidth={1.5}
                  label={{ value: 'threshold', position: 'right', fontSize: 11, fill: CHART_COLORS.critical }}
                />
                <Scatter data={anomalyTimeline} fill={CHART_COLORS.ink}>
                  {anomalyTimeline.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={entry.isAnomaly ? CHART_COLORS.critical : CHART_COLORS.inkSoft}
                      opacity={entry.isAnomaly ? 1 : 0.5}
                      r={entry.isAnomaly ? 5 : 3}
                    />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      <div className="dashboard-grid">
        {/* Events by Type - Horizontal Bar Chart */}
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
            <div style={{ width: '100%', height: Math.max(stats.events_by_type.length * 44, 120) }}>
              <ResponsiveContainer>
                <BarChart
                  data={stats.events_by_type.map((item) => ({ name: humanizeLabel(item.event_type), count: item.count }))}
                  layout="vertical"
                  margin={{ top: 0, right: 16, bottom: 0, left: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11, fill: CHART_COLORS.inkSoft }} stroke={CHART_COLORS.grid} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={100}
                    tick={{ fontSize: 12, fill: CHART_COLORS.ink }}
                    stroke="transparent"
                  />
                  <Tooltip content={<ChartTooltipContent />} />
                  <Bar dataKey="count" name="Events" radius={[0, 6, 6, 0]} barSize={20}>
                    {stats.events_by_type.map((_, i) => (
                      <Cell key={i} fill={TYPE_PALETTE[i % TYPE_PALETTE.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        {/* Events by Hour - Area Chart */}
        <Card className="stack-md">
          <div className="panel-header">
            <div className="panel-copy">
              <span className="panel-kicker">Rhythm</span>
              <h2 className="panel-title">Events by hour</h2>
              <p className="panel-summary">Time-of-day concentration across the selected range.</p>
            </div>
            <Badge variant="neutral">{activeRangeLabel}</Badge>
          </div>

          <div style={{ width: '100%', height: 240 }}>
            <ResponsiveContainer>
              <AreaChart data={hourData} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
                <defs>
                  <linearGradient id="hourGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={CHART_COLORS.ink} stopOpacity={0.15} />
                    <stop offset="95%" stopColor={CHART_COLORS.ink} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />
                <XAxis dataKey="hour" tick={{ fontSize: 10, fill: CHART_COLORS.inkSoft }} stroke={CHART_COLORS.grid} interval={2} />
                <YAxis tick={{ fontSize: 11, fill: CHART_COLORS.inkSoft }} stroke={CHART_COLORS.grid} />
                <Tooltip content={<ChartTooltipContent />} />
                <Area
                  type="monotone"
                  dataKey="count"
                  name="Events"
                  stroke={CHART_COLORS.ink}
                  strokeWidth={2}
                  fill="url(#hourGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Top Users */}
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
                    <tr
                      className="interactive-row cursor-pointer"
                      key={item.user_identifier}
                      onClick={() => navigate(`/users/${encodeURIComponent(item.user_identifier)}`)}
                    >
                      <td className="font-medium text-ink">{item.user_identifier}</td>
                      <td>
                        <div className="flex items-center gap-2">
                          <span>{formatCount(item.event_count)}</span>
                          <div className="h-1.5 flex-1 rounded-pill bg-canvas-warm">
                            <div
                              className="h-full rounded-pill bg-ink"
                              style={{ width: `${Math.min((item.event_count / Math.max(...stats.top_users.map((u) => u.event_count))) * 100, 100)}%` }}
                            />
                          </div>
                        </div>
                      </td>
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

        {/* Geo Distribution - Treemap */}
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
            <div style={{ width: '100%', height: 220 }}>
              <ResponsiveContainer>
                <Treemap
                  data={geoTreemap}
                  dataKey="size"
                  aspectRatio={4 / 3}
                  stroke={CHART_COLORS.surface}
                  content={({ x, y, width, height, name, count }: { x: number; y: number; width: number; height: number; name?: string; count?: number }) => {
                    if (width < 30 || height < 30) return <rect x={x} y={y} width={width} height={height} fill={CHART_COLORS.inkMuted} stroke={CHART_COLORS.surface} rx={4} />;
                    return (
                      <g>
                        <rect x={x} y={y} width={width} height={height} fill={CHART_COLORS.ink} stroke={CHART_COLORS.surface} rx={4} opacity={0.85} />
                        <text x={x + width / 2} y={y + height / 2 - 6} textAnchor="middle" fill={CHART_COLORS.surface} fontSize={13} fontWeight={500} letterSpacing="0.08em">
                          {name}
                        </text>
                        <text x={x + width / 2} y={y + height / 2 + 12} textAnchor="middle" fill="rgba(255,255,255,0.7)" fontSize={11}>
                          {count?.toLocaleString()}
                        </text>
                      </g>
                    );
                  }}
                />
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      {/* Recent Events table */}
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
                  <th>Score</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {recentEvents.map((event) => (
                  <tr
                    className="interactive-row cursor-pointer"
                    key={event.event_id}
                    onClick={() => navigate(`/users/${encodeURIComponent(event.user_identifier)}`)}
                  >
                    <td>{formatDateTime(event.occurred_at)}</td>
                    <td className="font-medium text-ink">{event.user_identifier}</td>
                    <td>
                      <Badge variant={event.is_anomaly ? 'critical' : 'neutral'}>
                        {humanizeLabel(event.event_type)}
                      </Badge>
                    </td>
                    <td>{event.source}</td>
                    <td>{event.source_ip ?? 'n/a'}</td>
                    <td className="tabular-nums">
                      {event.anomaly_score != null ? (
                        <span className={event.is_anomaly ? 'text-critical font-medium' : 'text-ink-muted'}>
                          {event.anomaly_score.toFixed(4)}
                        </span>
                      ) : (
                        <span className="text-ink-soft">--</span>
                      )}
                    </td>
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
