import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Navigate, useSearchParams } from 'react-router-dom';

import { useAuth } from '../../app/state/auth-context';
import { login } from '../../shared/api/auth';
import { API_BASE_URL } from '../../shared/lib/constants';
import { buildConsoleHandoffUrl } from '../../shared/lib/control-handoff';
import { AmbientBackground } from '../../shared/ui/AmbientBackground';
import { Button } from '../../shared/ui/button';
import { Card } from '../../shared/ui/card';
import { Input } from '../../shared/ui/input';

export function LoginPage() {
  const { token, username: currentUsername, setSession } = useAuth();
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('admin123');
  const [params] = useSearchParams();
  const returnTo = params.get('returnTo');

  const mutation = useMutation({
    mutationFn: async () => login(username, password),
    onSuccess: (result) => {
      setSession(result.access_token, username);
      if (returnTo) {
        window.location.assign(buildConsoleHandoffUrl(returnTo, result.access_token, username));
      }
    }
  });

  if (token && returnTo) {
    window.location.replace(buildConsoleHandoffUrl(returnTo, token, currentUsername));
    return null;
  }

  if (token && !returnTo) {
    return <Navigate to="/overview" replace />;
  }

  return (
    <div className="login-layout">
      <AmbientBackground variant="hero" />

      <div className="relative z-10 mx-auto grid w-full max-w-5xl gap-8 lg:grid-cols-[1.2fr_420px] lg:items-center">
        <section className="stack-md">
          <p className="inline-flex w-fit items-center rounded-pill border border-stroke bg-white px-3 py-1 text-sm font-semibold text-zinc-700">
            Aegis Risk Monitoring
          </p>
          <h1 className="text-balance text-5xl font-extrabold tracking-tight text-ink sm:text-6xl">
            Dead simple risk operations.
          </h1>
          <p className="max-w-2xl text-lg text-ink-muted">
            Sign in to monitor live anomalies, connector health, and model behavior from a clean operational cockpit.
          </p>
        </section>

        <Card className="login-card">
          <h2 className="text-2xl font-bold tracking-tight">Sign in</h2>
          <p className="muted">Use your account to access operational dashboards.</p>

          <label htmlFor="username">Username</label>
          <Input id="username" value={username} onChange={(event) => setUsername(event.target.value)} />

          <label htmlFor="password">Password</label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          <Button variant="primary" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? 'Signing in...' : 'Sign in'}
          </Button>

          <Button variant="secondary" onClick={() => window.location.assign(`${API_BASE_URL}/v1/auth/google/login`)}>
            Sign in with Google
          </Button>

          <Button variant="secondary" onClick={() => window.location.assign(`${API_BASE_URL}/v1/auth/apple/login`)}>
            Sign in with Apple
          </Button>

          {mutation.isError && <p className="inline-error">Authentication failed. Check credentials.</p>}
        </Card>
      </div>
    </div>
  );
}
