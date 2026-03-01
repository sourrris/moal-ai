import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useMemo } from 'react';
import { BrowserRouter } from 'react-router-dom';

import { AuthProvider } from '../state/auth-context';
import { LiveAlertsProvider } from '../state/live-alerts-context';
import { UIProvider } from '../state/ui-context';
import { ToastProvider, useToast } from '../../shared/ui/toaster';

// Inner component to properly inject the toast function into LiveAlertsProvider
function LiveAlertsWithToast({ children }: { children: React.ReactNode }) {
  const { toast } = useToast();
  return <LiveAlertsProvider toast={toast}>{children}</LiveAlertsProvider>;
}

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
            <ToastProvider>
              <LiveAlertsWithToast>{children}</LiveAlertsWithToast>
            </ToastProvider>
          </UIProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
