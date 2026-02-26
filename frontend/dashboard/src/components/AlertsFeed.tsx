import type { AlertMessage } from '../types/alert';

type Props = {
  alerts: AlertMessage[];
};

export function AlertsFeed({ alerts }: Props) {
  return (
    <div className="panel feed-panel">
      <h3>Live Alerts</h3>
      <div className="feed-list">
        {alerts.length === 0 && <p className="muted">No anomaly alerts received yet.</p>}
        {alerts.map((alert) => (
          <article key={alert.alert_id} className="feed-item">
            <header>
              <strong>{alert.tenant_id}</strong>
              <span>{new Date(alert.created_at).toLocaleTimeString()}</span>
            </header>
            <p>
              score: {alert.anomaly_score.toFixed(4)} | threshold: {alert.threshold.toFixed(4)}
            </p>
            <small>
              event {alert.event_id.slice(0, 8)} | {alert.model_name}:{alert.model_version}
            </small>
          </article>
        ))}
      </div>
    </div>
  );
}
