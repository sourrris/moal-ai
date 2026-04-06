import { LogOut } from 'lucide-react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';

import { useAuth } from '../../app/state/auth-context';
import { useUI } from '../../app/state/ui-context';
import { WINDOW_OPTIONS } from '../../shared/lib/constants';
import { AmbientBackground } from '../../shared/ui/AmbientBackground';
import { Button } from '../../shared/ui/button';
import { DensityToggle } from '../../shared/ui/DensityToggle';
import { Input } from '../../shared/ui/input';
import { Select } from '../../shared/ui/select';

const NAV_ITEMS = [
  { to: '/overview', label: 'Overview' },
  { to: '/alerts', label: 'Alerts' },
  { to: '/events', label: 'Events' },
  { to: '/models', label: 'Models' }
] as const;

export function AppShell() {
  const { clearSession, username } = useAuth();
  const { window: selectedWindow, setWindow } = useUI();
  const navigate = useNavigate();

  return (
    <div className="app-shell">
      <AmbientBackground variant="app" />

      <div className="relative z-10">
        <header className="app-topbar">
          <div className="app-topbar-inner">
            <button className="brand-chip" type="button" onClick={() => navigate('/overview')}>
              <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-zinc-900 text-[11px] font-bold text-white">
                M
              </span>
              <span>moal-ai</span>
            </button>

            <nav className="top-nav-links" aria-label="Primary">
              {NAV_ITEMS.map(({ to, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) => `top-nav-link ${isActive ? 'top-nav-link--active' : ''}`}
                >
                  {label}
                </NavLink>
              ))}
            </nav>

            <div className="ml-auto flex items-center gap-2">
              <span className="hidden text-sm text-zinc-600 md:inline">{username ?? 'Analyst'}</span>
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
          </div>

          <div className="app-topbar-mobile-row">
            <nav className="mobile-nav" aria-label="Primary mobile">
              {NAV_ITEMS.map(({ to, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) => `top-nav-link ${isActive ? 'top-nav-link--active' : ''}`}
                >
                  {label}
                </NavLink>
              ))}
            </nav>
          </div>
        </header>

        <section className="ops-bar-shell">
          <div className="ops-bar">
            <Input placeholder="Search events, alerts, model versions" aria-label="Global search" className="ops-search" />

            <Select value={selectedWindow} onChange={(event) => setWindow(event.target.value as typeof selectedWindow)}>
              {WINDOW_OPTIONS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </Select>

            <DensityToggle />
          </div>
        </section>

        <div className="app-shell-main">
          <main className="page-content">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
