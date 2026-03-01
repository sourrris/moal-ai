import { Keyboard } from 'lucide-react';
import { useState } from 'react';

import { useAuth } from '../../app/state/auth-context';
import { useUI } from '../../app/state/ui-context';
import { API_BASE_URL, WS_BASE_URL } from '../../shared/lib/constants';
import { Badge } from '../../shared/ui/badge';
import { Button } from '../../shared/ui/button';
import { DataPanel } from '../../shared/ui/DataPanel';
import { DensityToggle } from '../../shared/ui/DensityToggle';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../../shared/ui/dialog';
import { Select } from '../../shared/ui/select';
import { DashboardPageFrame } from '../../widgets/layout/DashboardPageFrame';

export function SettingsPage() {
  const { username } = useAuth();
  const { theme, setTheme, timezone, setTimezone, tenant, window, density } = useUI();
  const [openShortcuts, setOpenShortcuts] = useState(false);

  return (
    <DashboardPageFrame chips={<Badge variant="info">density {density}</Badge>}>
      <DataPanel title="Session" description="Current signed-in profile and environment diagnostics.">
        <div className="stack-sm">
          <p>
            User: <strong>{username ?? 'unknown'}</strong>
          </p>
          <p>
            Tenant: <strong>{tenant}</strong>
          </p>
          <p>
            Time window: <strong>{window}</strong>
          </p>
        </div>
      </DataPanel>

      <div className="grid-two">
        <DataPanel title="Display preferences" description="Theme, timezone, and density controls for your workspace.">
          <div className="stack-sm">
            <label htmlFor="theme">Theme</label>
            <Select id="theme" value={theme} onChange={(event) => setTheme(event.target.value as 'light' | 'dark')}>
              <option value="light">light</option>
              <option value="dark">dark (legacy)</option>
            </Select>

            <label htmlFor="timezone">Timezone</label>
            <Select
              id="timezone"
              value={timezone}
              onChange={(event) => setTimezone(event.target.value as 'local' | 'utc')}
            >
              <option value="local">local</option>
              <option value="utc">utc</option>
            </Select>

            <label>Density</label>
            <DensityToggle className="w-fit" />
          </div>
        </DataPanel>

        <DataPanel title="Endpoint diagnostics" description="Current API and websocket targets used by this session.">
          <div className="stack-sm">
            <p>
              API <Badge variant="info">{API_BASE_URL}</Badge>
            </p>
            <p>
              WebSocket <Badge variant="info">{WS_BASE_URL}</Badge>
            </p>
          </div>
        </DataPanel>
      </div>

      <DataPanel
        title="Keyboard shortcuts"
        description="Keyboard-first workflow support scaffolded for operational users."
        actions={
          <Button variant="secondary" onClick={() => setOpenShortcuts(true)}>
            <Keyboard size={14} />
            Open shortcuts
          </Button>
        }
      >
        <p className="muted">Open the shortcuts panel to review navigation and triage commands.</p>
      </DataPanel>

      <Dialog open={openShortcuts} onOpenChange={setOpenShortcuts}>
        <DialogContent>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>Use these shortcuts for faster triage.</DialogDescription>
          <ul className="shortcut-list">
            <li>
              <kbd>g</kbd>
              <span>then</span>
              <kbd>o</kbd>
              <span>Go to overview</span>
            </li>
            <li>
              <kbd>g</kbd>
              <span>then</span>
              <kbd>a</kbd>
              <span>Go to alerts</span>
            </li>
            <li>
              <kbd>/</kbd>
              <span>Focus global search</span>
            </li>
            <li>
              <kbd>i</kbd>
              <span>Ingest synthetic event</span>
            </li>
          </ul>
        </DialogContent>
      </Dialog>
    </DashboardPageFrame>
  );
}
