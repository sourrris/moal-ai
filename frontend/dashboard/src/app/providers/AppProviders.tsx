import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useMemo } from 'react';
import { BrowserRouter } from 'react-router-dom';

import { AuthProvider } from '../state/auth-context';
import { LiveAlertsProvider } from '../state/live-alerts-context';
import { UIProvider } from '../state/ui-context';

export function AppProviders({ children }: { children: React.ReactNode }) {
  const queryClient = useMemo(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            refetchOnWindowFocus: false,
            retry: 1
          }
        }
      }),
    []
  );

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <UIProvider>
            <LiveAlertsProvider>{children}</LiveAlertsProvider>
          </UIProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
