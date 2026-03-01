import { createContext, useContext } from 'react';

import type { AlertListItem } from '../../entities/alerts';
import type { LiveMetric } from '../../entities/metrics';
import { useRiskStream } from '../../shared/hooks/useRiskStream';
import { useAuth } from './auth-context';
import { useUI } from './ui-context';
import type { useToast } from '../../shared/ui/toaster';

type LiveAlertsState = {
  connected: boolean;
  stale: boolean;
  alerts: AlertListItem[];
  metrics: LiveMetric[];
};

const LiveAlertsContext = createContext<LiveAlertsState | null>(null);

interface LiveAlertsProviderProps {
  children: React.ReactNode;
  toast?: ReturnType<typeof useToast>['toast'];
}

export function LiveAlertsProvider({ children, toast }: LiveAlertsProviderProps) {
  const { token } = useAuth();
  const { tenant } = useUI();
  const live = useRiskStream(token, tenant, toast);
  return <LiveAlertsContext.Provider value={live}>{children}</LiveAlertsContext.Provider>;
}

export function useLiveAlertState() {
  const context = useContext(LiveAlertsContext);
  if (!context) {
    throw new Error('useLiveAlertState must be used inside LiveAlertsProvider');
  }
  return context;
}
