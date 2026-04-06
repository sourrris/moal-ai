import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useMemo } from 'react';
import { BrowserRouter } from 'react-router-dom';

import { AuthProvider } from '../state/auth-context';
import { UIProvider } from '../state/ui-context';

const routerFuture = {
  v7_startTransition: true,
  v7_relativeSplatPath: true,
} as const;

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
      <BrowserRouter future={routerFuture}>
        <AuthProvider>
          <UIProvider>
            {children}
          </UIProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
