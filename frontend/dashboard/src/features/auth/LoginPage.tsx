import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Navigate } from 'react-router-dom';

import { useAuth } from '../../app/state/auth-context';
import { login } from '../../shared/api/auth';
import { Button } from '../../shared/ui/button';
import { Card } from '../../shared/ui/card';
import { Input } from '../../shared/ui/input';

export function LoginPage() {
  const { token, setSession } = useAuth();
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('admin123');

  const mutation = useMutation({
    mutationFn: async () => login(username, password),
    onSuccess: (result) => setSession(result.access_token, username)
  });

  if (token) {
    return <Navigate to="/overview" replace />;
  }

  return (
    <div className="login-layout">
      <Card className="login-card">
        <h1>Aegis Risk Console</h1>
        <p className="muted">Authenticate to access operational monitoring views.</p>

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

        {mutation.isError && <p className="inline-error">Authentication failed. Check credentials.</p>}
      </Card>
    </div>
  );
}
