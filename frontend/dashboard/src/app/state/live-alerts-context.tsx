import { createContext, useContext } from 'react';

import type { AlertListItem } from '../../entities/alerts';
import { useLiveAlerts } from '../../shared/hooks/useLiveAlerts';
import { useAuth } from './auth-context';

type LiveAlertsState = {
  connected: boolean;
  stale: boolean;
  alerts: AlertListItem[];
};

const LiveAlertsContext = createContext<LiveAlertsState | null>(null);

export function LiveAlertsProvider({ children }: { children: React.ReactNode }) {
  const { token } = useAuth();
  const live = useLiveAlerts(token);
  return <LiveAlertsContext.Provider value={live}>{children}</LiveAlertsContext.Provider>;
}

export function useLiveAlertState() {
  const context = useContext(LiveAlertsContext);
  if (!context) {
    throw new Error('useLiveAlertState must be used inside LiveAlertsProvider');
  }
  return context;
}
