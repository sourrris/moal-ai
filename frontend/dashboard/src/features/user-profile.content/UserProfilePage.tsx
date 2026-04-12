import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
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
  XAxis,
  YAxis
} from 'recharts';

import { useAuth } from '../../app/state/auth-context';
import { fetchUserProfile } from '../../shared/api/users';
import { Badge } from '../../shared/ui/badge';
import { Button } from '../../shared/ui/button';
import { Card } from '../../shared/ui/card';
import { KpiCard } from '../../shared/ui/KpiCard';
import { DashboardPageFrame } from '../../widgets/layout/DashboardPageFrame';

const CHART_COLORS = {
  ink: '#000000',
  inkMuted: '#4e4e4e',
  inkSoft: '#777169',
  critical: '#9c4139',
  warning: '#8a6539',
  success: '#2f7f56',
  grid: '#e5e5e5',
  surface: '#ffffff'
};

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

export function UserProfilePage() {
  const { identifier } = useParams<{ identifier: string }>();
  const { token } = useAuth();
  const navigate = useNavigate();

  const profileQuery = useQuery({
    queryKey: ['user-profile', identifier],
    queryFn: async () => fetchUserProfile(token!, identifier!),
    enabled: Boolean(token) && Boolean(identifier),
    refetchInterval: 30_000
  });

  if (!identifier) {
    return <p className="inline-error">No user identifier provided.</p>;
  }

  if (profileQuery.isLoading) {
    return <p className="muted">Loading user profile...</p>;
  }

  if (profileQuery.isError || !profileQuery.data) {
    return <p className="inline-error">Unable to load profile for {identifier}.</p>;
  }

  const profile = profileQuery.data;

  // Anomaly score timeline from events (chronological order)
  const anomalyTimeline = [...profile.recent_events]
    .filter((e) => e.anomaly_score != null)
    .reverse()
    .map((e) => ({
      time: new Date(e.occurred_at).getTime(),
      label: formatDateTimeShort(e.occurred_at),
      score: e.anomaly_score ?? 0,
      isAnomaly: e.is_anomaly ?? false,
      threshold: e.threshold ?? 0
    }));

  const maxThreshold = Math.max(...anomalyTimeline.map((p) => p.threshold), 0.5);

  // Hourly pattern data
  const hourData = profile.hourly_pattern.map((h) => ({
    hour: formatHour(h.hour),
    count: h.count
  }));

  return (
    <DashboardPageFrame
      eyebrow="User profile"
      title={identifier}
      subtitle={
        profile.first_seen && profile.last_seen
          ? `Active from ${formatDateTime(profile.first_seen)} to ${formatDateTime(profile.last_seen)}`
          : 'No activity recorded'
      }
      chips={
        <div className="inline-actions">
          <Badge variant={profile.total_anomalies > 0 ? 'critical' : 'success'}>
            {profile.total_anomalies} anomalies
          </Badge>
          <Badge variant="neutral">{profile.total_events} events</Badge>
        </div>
      }
      actions={
        <Button variant="secondary" onClick={() => navigate(-1)}>
          Back
        </Button>
      }
    >
      {/* KPI cards */}
      <div className="kpi-grid">
        <KpiCard label="Total events" value={profile.total_events.toLocaleString()} meta="all time" />
        <KpiCard
          label="Anomalies"
          value={profile.total_anomalies.toLocaleString()}
          meta="flagged events"
          trend={profile.total_anomalies > 0 ? 'up' : 'neutral'}
        />
        <KpiCard
          label="Avg score"
          value={profile.avg_anomaly_score?.toFixed(4) ?? 'n/a'}
          meta="mean anomaly score"
        />
        <KpiCard label="Unique IPs" value={profile.unique_ips.toLocaleString()} meta="source addresses" />
        <KpiCard label="Unique devices" value={profile.unique_devices.toLocaleString()} meta="fingerprints seen" />
      </div>

      {/* Anomaly score timeline */}
      {anomalyTimeline.length > 0 && (
        <Card className="stack-md">
          <div className="panel-header">
            <div className="panel-copy">
              <span className="panel-kicker">Signal</span>
              <h2 className="panel-title">Anomaly score history</h2>
              <p className="panel-summary">Reconstruction error for each scored event. Red points exceeded the threshold.</p>
            </div>
          </div>

          <div style={{ width: '100%', height: 260 }}>
            <ResponsiveContainer>
              <ScatterChart margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />
                <XAxis
                  dataKey="time"
                  type="number"
                  domain={['dataMin', 'dataMax']}
                  tickFormatter={(t: number) =>
                    new Date(t).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
                  }
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
                        <p className="text-ink-muted">Threshold: {d.threshold.toFixed(4)}</p>
                        {d.isAnomaly && <p className="font-medium text-critical">Anomaly detected</p>}
                      </div>
                    );
                  }}
                />
                <ReferenceLine
                  y={maxThreshold}
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
                    />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      <div className="dashboard-grid">
        {/* Hourly activity pattern */}
        <Card className="stack-md">
          <div className="panel-header">
            <div className="panel-copy">
              <span className="panel-kicker">Behavior pattern</span>
              <h2 className="panel-title">Activity by hour</h2>
              <p className="panel-summary">When this user is typically active. Unusual hours may indicate compromise.</p>
            </div>
          </div>

          <div style={{ width: '100%', height: 200 }}>
            <ResponsiveContainer>
              <AreaChart data={hourData} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
                <defs>
                  <linearGradient id="userHourGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={CHART_COLORS.ink} stopOpacity={0.15} />
                    <stop offset="95%" stopColor={CHART_COLORS.ink} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />
                <XAxis dataKey="hour" tick={{ fontSize: 10, fill: CHART_COLORS.inkSoft }} stroke={CHART_COLORS.grid} interval={2} />
                <YAxis tick={{ fontSize: 11, fill: CHART_COLORS.inkSoft }} stroke={CHART_COLORS.grid} />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    return (
                      <div className="rounded-panel border border-black/5 bg-white px-3 py-2 text-[0.82rem] shadow-outline">
                        <p className="text-ink-soft">{label}</p>
                        <p className="text-ink"><span className="font-medium">Events:</span> {payload[0].value}</p>
                      </div>
                    );
                  }}
                />
                <Area type="monotone" dataKey="count" stroke={CHART_COLORS.ink} strokeWidth={2} fill="url(#userHourGradient)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Event type breakdown */}
        <Card className="stack-md">
          <div className="panel-header">
            <div className="panel-copy">
              <span className="panel-kicker">Activity mix</span>
              <h2 className="panel-title">Event types</h2>
              <p className="panel-summary">Distribution of behavior categories for this user.</p>
            </div>
          </div>

          {profile.event_types.length === 0 ? (
            <div className="empty-state">No events recorded.</div>
          ) : (
            <div style={{ width: '100%', height: Math.max(profile.event_types.length * 44, 100) }}>
              <ResponsiveContainer>
                <BarChart
                  data={profile.event_types.map((t) => ({ name: humanizeLabel(t.event_type), count: t.count }))}
                  layout="vertical"
                  margin={{ top: 0, right: 16, bottom: 0, left: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11, fill: CHART_COLORS.inkSoft }} stroke={CHART_COLORS.grid} />
                  <YAxis type="category" dataKey="name" width={90} tick={{ fontSize: 12, fill: CHART_COLORS.ink }} stroke="transparent" />
                  <Tooltip
                    content={({ active, payload, label }) => {
                      if (!active || !payload?.length) return null;
                      return (
                        <div className="rounded-panel border border-black/5 bg-white px-3 py-2 text-[0.82rem] shadow-outline">
                          <p className="text-ink-soft">{label}</p>
                          <p className="text-ink"><span className="font-medium">Count:</span> {payload[0].value}</p>
                        </div>
                      );
                    }}
                  />
                  <Bar dataKey="count" name="Events" radius={[0, 6, 6, 0]} barSize={20} fill={CHART_COLORS.ink} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        {/* Source IPs */}
        <Card className="stack-md">
          <div className="panel-header">
            <div className="panel-copy">
              <span className="panel-kicker">Network</span>
              <h2 className="panel-title">Source IPs</h2>
              <p className="panel-summary">IP addresses this user has connected from.</p>
            </div>
          </div>

          {profile.source_ips.length === 0 ? (
            <div className="empty-state">No IP data recorded.</div>
          ) : (
            <div className="dashboard-stat-list">
              {profile.source_ips.map((ip) => (
                <div className="dashboard-stat-pair" key={ip.ip}>
                  <span className="font-mono text-[0.88rem] text-ink">{ip.ip}</span>
                  <span className="dashboard-stat-value">{ip.count.toLocaleString()}</span>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Countries */}
        <Card className="stack-md">
          <div className="panel-header">
            <div className="panel-copy">
              <span className="panel-kicker">Geography</span>
              <h2 className="panel-title">Countries</h2>
              <p className="panel-summary">Observed source countries for this user's activity.</p>
            </div>
          </div>

          {profile.countries.length === 0 ? (
            <div className="empty-state">No geo data recorded.</div>
          ) : (
            <div className="dashboard-stat-list">
              {profile.countries.map((c) => (
                <div className="dashboard-stat-pair" key={c.country}>
                  <span className="dashboard-stat-label">{c.country.toUpperCase()}</span>
                  <span className="dashboard-stat-value">{c.count.toLocaleString()}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Recent events timeline */}
      <Card className="stack-md">
        <div className="panel-header">
          <div className="panel-copy">
            <span className="panel-kicker">Timeline</span>
            <h2 className="panel-title">Recent events</h2>
            <p className="panel-summary">Latest 100 events for this user with anomaly context.</p>
          </div>
        </div>

        {profile.recent_events.length === 0 ? (
          <div className="empty-state">No events recorded for this user.</div>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead className="sticky-table-head">
                <tr>
                  <th>Time</th>
                  <th>Type</th>
                  <th>Source</th>
                  <th>IP</th>
                  <th>Country</th>
                  <th>Score</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {profile.recent_events.map((event) => (
                  <tr className="interactive-row" key={event.event_id}>
                    <td>{formatDateTime(event.occurred_at)}</td>
                    <td>
                      <Badge variant={event.is_anomaly ? 'critical' : 'neutral'}>
                        {humanizeLabel(event.event_type)}
                      </Badge>
                    </td>
                    <td>{event.source}</td>
                    <td className="font-mono text-[0.88rem]">{event.source_ip ?? 'n/a'}</td>
                    <td>{event.geo_country?.toUpperCase() ?? '--'}</td>
                    <td className="tabular-nums">
                      {event.anomaly_score != null ? (
                        <span className={event.is_anomaly ? 'font-medium text-critical' : 'text-ink-muted'}>
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
                            : event.failed_auth_count > 0
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
