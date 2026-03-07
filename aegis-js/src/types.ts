export type StandardizedTransaction = {
  transaction_id: string;
  tenant_id: string;
  source: string;
  amount: number;
  currency: string;
  timestamp: string;
  counterparty_id?: string | null;
  metadata_json?: Record<string, unknown>;
};

export type PlatformIngestRequest = {
  connector?: string;
  source?: string;
  payload?: Record<string, unknown>;
  transaction?: StandardizedTransaction;
  event_type?: string;
  idempotency_key?: string;
  occurred_at?: string;
};

export type EventIngestResult = {
  event_id: string;
  status: 'accepted' | 'duplicate' | 'failed' | string;
  queued: boolean;
};

export type PlatformAlert = Record<string, unknown>;

export type PlatformAlertList = {
  items: PlatformAlert[];
  next_cursor: string | null;
  total_estimate: number;
};

export type PlatformConfig = {
  tenant_id: string;
  anomaly_threshold: number | null;
  enabled_connectors: string[];
  model_version: string | null;
  rule_overrides_json: Record<string, unknown>;
  connector_modules_loaded: string[];
};
