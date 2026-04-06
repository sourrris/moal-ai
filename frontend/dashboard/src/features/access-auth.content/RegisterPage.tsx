import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';

import { useAuth } from '../../app/state/auth-context';
import { register } from '../../shared/api/auth';
import { AmbientBackground } from '../../shared/ui/AmbientBackground';
import { Button } from '../../shared/ui/button';
import { Card } from '../../shared/ui/card';
import { Input } from '../../shared/ui/input';

export function RegisterPage() {
  const navigate = useNavigate();
  const { token, setSession } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const mutation = useMutation({
    mutationFn: async () => register(username, password),
    onSuccess: (result) => {
      setSession(result.access_token, username);
      navigate('/overview', { replace: true });
    }
  });

  if (token) {
    return <Navigate to="/overview" replace />;
  }

  return (
    <div className="login-layout">
      <AmbientBackground variant="hero" />

      <div className="relative z-10 mx-auto grid w-full max-w-5xl gap-8 lg:grid-cols-[1.2fr_420px] lg:items-center">
        <section className="stack-md">
          <p className="inline-flex w-fit items-center rounded-pill border border-stroke bg-white px-3 py-1 text-sm font-semibold text-zinc-700">
            moal-ai
          </p>
          <h1 className="text-balance text-5xl font-extrabold tracking-tight text-ink sm:text-6xl">
            Create your account.
          </h1>
          <p className="max-w-2xl text-lg text-ink-muted">
            Get started monitoring user behavior anomalies and investigating security alerts.
          </p>
        </section>

        <Card className="login-card">
          <h2 className="text-2xl font-bold tracking-tight">Create account</h2>
          <p className="muted">Sign up to access the dashboard.</p>

          <label htmlFor="register-username">Username</label>
          <Input id="register-username" value={username} onChange={(event) => setUsername(event.target.value)} />

          <label htmlFor="register-password">Password</label>
          <Input
            id="register-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          <Button variant="primary" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? 'Creating account...' : 'Create account'}
          </Button>

          <p className="muted">
            Already have access? <Link to="/login">Sign in</Link>
          </p>

          {mutation.isError && <p className="inline-error">{(mutation.error as Error).message}</p>}
        </Card>
      </div>
    </div>
  );
}
