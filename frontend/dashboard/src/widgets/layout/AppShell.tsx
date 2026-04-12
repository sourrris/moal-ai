import { LogOut } from 'lucide-react';
import { Outlet, useNavigate } from 'react-router-dom';

import { useAuth } from '../../app/state/auth-context';
import { AmbientBackground } from '../../shared/ui/AmbientBackground';
import { Button } from '../../shared/ui/button';

export function AppShell() {
  const { clearSession, username } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="app-shell">
      <AmbientBackground variant="app" />

      <div className="relative z-10">
        <header className="app-topbar">
          <div className="app-topbar-inner">
            <button className="brand-chip" type="button" onClick={() => navigate('/')}>
              <span className="brand-chip-mark">
                M
              </span>
              <span className="brand-chip-copy">
                <span className="brand-chip-label">moal-ai</span>
                <span className="brand-chip-meta">behavior intelligence</span>
              </span>
            </button>

            <div className="topbar-copy">
              <p className="topbar-copy-line">
                All-time anomaly visibility with date controls, recent activity, and investigation-ready signal density.
              </p>
            </div>

            <div className="topbar-actions">
              <span className="topbar-user">{username ?? 'Analyst'}</span>
              <Button
                variant="secondary"
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
        </header>

        <div className="app-shell-main">
          <main className="page-content">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
