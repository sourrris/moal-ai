import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, Navigate } from 'react-router-dom';

import { useAuth } from '../../app/state/auth-context';
import { login } from '../../shared/api/auth';
import { AmbientBackground } from '../../shared/ui/AmbientBackground';
import { Button } from '../../shared/ui/button';
import { Card } from '../../shared/ui/card';
import { Input } from '../../shared/ui/input';

export function LoginPage() {
  const { token, setSession } = useAuth();
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('admin123');

  const mutation = useMutation({
    mutationFn: async () => login(username, password),
    onSuccess: (result) => {
      setSession(result.access_token, username);
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
          <span className="page-eyebrow">Risk operations workspace</span>
          <h1 className="display-hero">Spot quiet deviations before they become incidents.</h1>
          <p className="auth-copy">
            Monitor user behavior anomalies, read event pressure at a glance, and move from broad all-time visibility
            into narrow investigation windows without changing screens.
          </p>

          <div className="auth-rail">
            <article className="auth-rail-card">
              <span className="auth-rail-label">Default scope</span>
              <strong className="auth-rail-value">All time</strong>
              <span className="auth-rail-copy">Historical seed data and live demo activity surface together by default.</span>
            </article>
            <article className="auth-rail-card">
              <span className="auth-rail-label">Signal</span>
              <strong className="auth-rail-value">575+</strong>
              <span className="auth-rail-copy">Behavior events already mapped for anomaly review in the local stack.</span>
            </article>
            <article className="auth-rail-card">
              <span className="auth-rail-label">Flow</span>
              <strong className="auth-rail-value">30s</strong>
              <span className="auth-rail-copy">Live refresh keeps recent behavior, alert counts, and top users current.</span>
            </article>
          </div>
        </section>

        <Card className="login-card">
          <div className="auth-card-intro">
            <span className="page-eyebrow">Sign in</span>
            <h2 className="display-card">Access the behavior board.</h2>
            <p className="muted">Use your analyst account to enter the dashboard.</p>
          </div>

          <div className="auth-form">
            <div className="field-group">
              <label htmlFor="username">Username</label>
              <Input id="username" value={username} onChange={(event) => setUsername(event.target.value)} />
            </div>

            <div className="field-group">
              <label htmlFor="password">Password</label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>

            <Button variant="warm" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
              {mutation.isPending ? 'Signing in...' : 'Enter dashboard'}
            </Button>
          </div>

          <p className="auth-footer">
            Local default credentials: <span className="mono">admin / admin123</span>
          </p>
          <p className="auth-footer">
            New here?{' '}
            <Link className="auth-link" to="/register">
              Create an account
            </Link>
          </p>

          {mutation.isError && <p className="inline-error">Authentication failed. Check credentials.</p>}
        </Card>
      </div>
    </div>
  );
}
