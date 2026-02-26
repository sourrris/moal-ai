import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { AlertMessage } from '../types/alert';

type Props = {
  alerts: AlertMessage[];
};

export function AlertsChart({ alerts }: Props) {
  const chartData = alerts
    .slice(0, 40)
    .reverse()
    .map((alert) => ({
      time: new Date(alert.created_at).toLocaleTimeString(),
      score: Number(alert.anomaly_score.toFixed(4)),
      threshold: Number(alert.threshold.toFixed(4))
    }));

  return (
    <div className="panel chart-panel">
      <h3>Anomaly Score Stream</h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData}>
          <XAxis dataKey="time" hide />
          <YAxis width={45} />
          <Tooltip />
          <Line type="monotone" dataKey="score" stroke="#ff7a18" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="threshold" stroke="#00a6a6" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
