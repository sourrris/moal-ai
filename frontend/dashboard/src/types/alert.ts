export type AlertMessage = {
  alert_id: string;
  event_id: string;
  tenant_id: string;
  severity: string;
  model_name: string;
  model_version: string;
  anomaly_score: number;
  threshold: number;
  created_at: string;
};
