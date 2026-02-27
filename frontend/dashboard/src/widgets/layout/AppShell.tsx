import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Bell, LayoutDashboard, LogOut, Radar, Settings, ShieldAlert, ShieldCheck } from 'lucide-react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';

import { useAuth } from '../../app/state/auth-context';
import { useLiveAlertState } from '../../app/state/live-alerts-context';
import { useUI } from '../../app/state/ui-context';
import { ingestSyntheticEvent } from '../../shared/api/alerts';
import { TENANT_OPTIONS, WINDOW_OPTIONS } from '../../shared/lib/constants';
import { Badge } from '../../shared/ui/badge';
import { Button } from '../../shared/ui/button';
import { Input } from '../../shared/ui/input';
import { Select } from '../../shared/ui/select';

const NAV_ITEMS = [
  { to: '/overview', label: 'Overview', icon: LayoutDashboard },
  { to: '/alerts', label: 'Alerts', icon: ShieldAlert },
  { to: '/events', label: 'Events', icon: Radar },
  { to: '/models', label: 'Models', icon: ShieldCheck },
  { to: '/settings', label: 'Settings', icon: Settings }
];

export function AppShell() {
  const { clearSession, token, username } = useAuth();
  const { tenant, setTenant, window, setWindow } = useUI();
  const { connected, stale, alerts } = useLiveAlertState();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();

  const ingestMutation = useMutation({
    mutationFn: async () => {
      if (!token) {
        throw new Error('No auth token');
      }
      return ingestSyntheticEvent(token, tenant);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['overview-metrics'] });
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      queryClient.invalidateQueries({ queryKey: ['events'] });
    }
  });

  const pageTitle = NAV_ITEMS.find((item) => location.pathname.startsWith(item.to))?.label ?? 'Overview';

  return (
    <div className="shell">
      <aside className="shell-sidebar">
        <div className="brand">
          <span className="brand-logo">AR</span>
          <div>
            <p className="brand-title">Aegis Risk</p>
            <p className="brand-subtitle">Monitoring Console</p>
          </div>
        </div>

        <nav className="nav-list">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => `nav-item ${isActive ? 'nav-item--active' : ''}`}>
              <Icon size={16} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <p className="sidebar-user">{username ?? 'Analyst'}</p>
          <Button
            variant="ghost"
            onClick={() => {
              clearSession();
              navigate('/login');
            }}
          >
            <LogOut size={14} />
            Sign out
          </Button>
        </div>
      </aside>

      <div className="shell-main">
        <header className="command-bar">
          <div className="command-left">
            <h1>{pageTitle}</h1>
            <Input placeholder="Search events, alerts, model versions" aria-label="Global search" />
          </div>

          <div className="command-actions">
            <Select value={tenant} onChange={(event) => setTenant(event.target.value as typeof tenant)}>
              {TENANT_OPTIONS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </Select>

            <Select value={window} onChange={(event) => setWindow(event.target.value as typeof window)}>
              {WINDOW_OPTIONS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </Select>

            <Badge variant={connected ? (stale ? 'warning' : 'success') : 'critical'}>
              {connected ? (stale ? 'socket stale' : 'socket live') : 'socket offline'}
            </Badge>

            <Button variant="primary" onClick={() => ingestMutation.mutate()} disabled={ingestMutation.isPending}>
              <Bell size={14} />
              {ingestMutation.isPending ? 'Ingesting...' : 'Ingest Event'}
            </Button>
          </div>
        </header>

        {ingestMutation.isError && <p className="inline-error">Failed to ingest synthetic event.</p>}
        {!connected && <p className="inline-warning">Live stream disconnected. Reconnect is running in background.</p>}

        {alerts.length > 0 && (
          <div className="live-strip" role="status" aria-live="polite">
            <strong>Live:</strong>
            <span>
              {alerts[0].tenant_id} {alerts[0].severity} alert score {alerts[0].anomaly_score.toFixed(4)}
            </span>
          </div>
        )}

        <main className="page-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
