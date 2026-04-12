import { LogOut } from 'lucide-react';
import { Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../../app/state/auth-context";
import { AmbientBackground } from "../../shared/ui/AmbientBackground";
import { Button } from "../../shared/ui/button";

export function AppShell() {
  const { clearSession, username } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="app-shell">
      <AmbientBackground variant="app" />

      <div className="relative z-10">
        <header className="app-topbar">
          <div className="app-topbar-inner">
            <button
              className="brand-chip"
              type="button"
              onClick={() => navigate("/")}
            >
              <span className="brand-chip-mark">M</span>
              <span className="brand-chip-copy">
                <span className="brand-chip-label">moal-ai</span>
                <span className="brand-chip-meta">behavior intelligence</span>
              </span>
            </button>

            <nav className="topbar-nav">
              <button type="button" className="topbar-nav-link" onClick={() => navigate('/')}>Overview</button>
              <button type="button" className="topbar-nav-link" onClick={() => navigate('/alerts')}>Alerts</button>
              <button type="button" className="topbar-nav-link" onClick={() => navigate('/models')}>Models</button>
            </nav>

            <div className="topbar-actions">
              <span className="topbar-user">{username ?? "Analyst"}</span>
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
