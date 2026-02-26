import { useMemo, useState } from 'react';
import { AlertsChart } from './components/AlertsChart';
import { AlertsFeed } from './components/AlertsFeed';
import { useAlertsSocket } from './hooks/useAlertsSocket';
import { ingestSyntheticEvent, login } from './services/api';

export default function App() {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('admin123');
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const { connected, alerts } = useAlertsSocket(token);

  const stats = useMemo(() => {
    const lastTen = alerts.slice(0, 10);
    const avgScore =
      lastTen.length > 0 ? lastTen.reduce((sum, item) => sum + item.anomaly_score, 0) / lastTen.length : 0;

    return {
      totalAlerts: alerts.length,
      avgScore
    };
  }, [alerts]);

  async function handleLogin() {
    setBusy(true);
    setError(null);
    try {
      const result = await login(username, password);
      setToken(result.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unexpected login error');
    } finally {
      setBusy(false);
    }
  }

  async function handleSendEvent() {
    if (!token) {
      return;
    }

    setBusy(true);
    setError(null);
    try {
      await ingestSyntheticEvent(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unexpected ingestion error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="hero">
        <h1>Real-Time AI Risk Monitoring</h1>
        <p>Live anomaly telemetry with event-driven backend processing.</p>
      </section>

      <section className="panel controls-panel">
        <div className="controls-grid">
          <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="username" />
          <input
            value={password}
            type="password"
            onChange={(e) => setPassword(e.target.value)}
            placeholder="password"
          />
          <button disabled={busy} onClick={handleLogin}>
            {token ? 'Re-authenticate' : 'Authenticate'}
          </button>
          <button disabled={busy || !token} onClick={handleSendEvent}>
            Ingest Synthetic Event
          </button>
        </div>

        <div className="kpis">
          <div className="kpi-tile">
            <span>Socket</span>
            <strong>{connected ? 'Connected' : 'Disconnected'}</strong>
          </div>
          <div className="kpi-tile">
            <span>Total Alerts</span>
            <strong>{stats.totalAlerts}</strong>
          </div>
          <div className="kpi-tile">
            <span>Avg Score (last 10)</span>
            <strong>{stats.avgScore.toFixed(4)}</strong>
          </div>
        </div>

        {error && <p className="error">{error}</p>}
      </section>

      <section className="dashboard-grid">
        <AlertsChart alerts={alerts} />
        <AlertsFeed alerts={alerts} />
      </section>
    </main>
  );
}
