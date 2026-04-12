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
      navigate('/', { replace: true });
    }
  });

  if (token) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="login-layout">
      <AmbientBackground variant="hero" />

      <div className="auth-shell">
        <section className="auth-hero">
          <span className="page-eyebrow">Account setup</span>
          <h1 className="display-hero">Open a calmer view into user behavior risk.</h1>
          <p className="auth-copy">
            Create an account to move through broad anomaly trends, user concentration, and recent event context with a
            single all-time dashboard that can tighten to exact date and time ranges when needed.
          </p>

          <div className="auth-rail">
            <article className="auth-rail-card">
              <span className="auth-rail-label">Overview</span>
              <strong className="auth-rail-value">Single screen</strong>
              <span className="auth-rail-copy">Volume, alert pressure, geography, and recent activity live together.</span>
            </article>
            <article className="auth-rail-card">
              <span className="auth-rail-label">Controls</span>
              <strong className="auth-rail-value">Custom windows</strong>
              <span className="auth-rail-copy">Analysts can narrow the board from all-time into exact investigation ranges.</span>
            </article>
            <article className="auth-rail-card">
              <span className="auth-rail-label">Refresh</span>
              <strong className="auth-rail-value">Live</strong>
              <span className="auth-rail-copy">Recent events continue to stream while the rest of the board stays readable.</span>
            </article>
          </div>
        </section>

        <Card className="login-card">
          <div className="auth-card-intro">
            <span className="page-eyebrow">Register</span>
            <h2 className="display-card">Create an analyst account.</h2>
            <p className="muted">Sign up to enter the dashboard and start reviewing behavior patterns.</p>
          </div>

          <div className="auth-form">
            <div className="field-group">
              <label htmlFor="register-username">Username</label>
              <Input id="register-username" value={username} onChange={(event) => setUsername(event.target.value)} />
            </div>

            <div className="field-group">
              <label htmlFor="register-password">Password</label>
              <Input
                id="register-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>

            <Button variant="warm" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
              {mutation.isPending ? 'Creating account...' : 'Create account'}
            </Button>
          </div>

          <p className="auth-footer">
            Already have access?{' '}
            <Link className="auth-link" to="/login">
              Sign in
            </Link>
          </p>

          {mutation.isError && <p className="inline-error">{(mutation.error as Error).message}</p>}
        </Card>
      </div>
    </div>
  );
}
