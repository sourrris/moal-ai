import { useEffect } from 'react';
import { Navigate, useSearchParams } from 'react-router-dom';

import { useAuth } from '../../app/state/auth-context';
import { AmbientBackground } from '../../shared/ui/AmbientBackground';
import { Card } from '../../shared/ui/card';

export function AuthCallbackPage() {
  const { token, setSession } = useAuth();
  const [params] = useSearchParams();

  useEffect(() => {
    const accessToken = params.get('token');
    const username = params.get('username');

    if (accessToken && username) {
      setSession(accessToken, username);
    }
  }, [params, setSession]);

  if (token) {
    return <Navigate to="/overview" replace />;
  }

  return (
    <div className="login-layout">
      <AmbientBackground variant="hero" />
      <Card className="login-card">
        <h1 className="text-3xl font-bold tracking-tight">Completing sign in...</h1>
        <p className="muted">We are verifying your session and redirecting you to the dashboard.</p>
      </Card>
    </div>
  );
}
