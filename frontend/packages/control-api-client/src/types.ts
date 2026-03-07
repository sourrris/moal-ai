export type TenantConfigurationDTO = {
  tenant_id: string;
  anomaly_threshold: number | null;
  enabled_connectors: string[];
  model_version: string | null;
  rule_overrides_json: RuleOverridesDTO;
  version: number;
  updated_at: string;
};

export type RuleOverridesDTO = {
  high_amount_threshold?: number;
  high_amount_weight?: number;
  sanctions_weight?: number;
  pep_weight?: number;
  proxy_ip_weight?: number;
  bin_mismatch_weight?: number;
  jurisdiction_threshold?: number;
  jurisdiction_weight?: number;
  cross_border_weight?: number;
};

export type TenantSummary = {
  tenant_id: string;
  display_name: string;
  status: string;
  tier: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at?: string | null;
};

export type ConnectorCatalogItem = {
  source_name: string;
  source_type: string;
  enabled: boolean;
  cadence_seconds: number;
  freshness_slo_seconds?: number | null;
  latest_status?: string | null;
  latest_run_at?: string | null;
};

export type AlertDestinationDTO = {
  destination_id: string;
  tenant_id: string;
  channel: 'webhook' | 'email' | 'slack';
  name: string;
  enabled: boolean;
  config: Record<string, unknown>;
  verification_status: 'pending' | 'verified' | 'failed' | string;
  last_tested_at: string | null;
  updated_at: string;
};

export type ReconciliationSummaryDTO = {
  tenant_id: string;
  from_ts: string;
  to_ts: string;
  ingested_events: number;
  processed_decisions: number;
  raised_alerts: number;
  delivered_alerts: number;
  failed_deliveries: number;
  mismatch_count: number;
};

export type TenantCreateRequest = {
  tenant_id: string;
  display_name: string;
  status?: string;
  tier?: string;
  metadata_json?: Record<string, unknown>;
};

export type TenantUpdateRequest = {
  display_name?: string;
  status?: string;
  tier?: string;
  metadata_json?: Record<string, unknown>;
};

export type ConnectorRunNowResponse = {
  source_name: string;
  status?: string;
  [key: string]: unknown;
};

export type DeliveryLogItemDTO = {
  delivery_id: string;
  tenant_id: string;
  destination_id?: string | null;
  channel: 'webhook' | 'email' | 'slack';
  alert_key: string;
  event_id?: string | null;
  status: string;
  attempt_no: number;
  response_code?: number | null;
  error_message?: string | null;
  payload_json: Record<string, unknown>;
  is_test: boolean;
  attempted_at: string;
  delivered_at?: string | null;
};

export type ConfigAuditItemDTO = {
  id: number;
  tenant_id?: string | null;
  actor: string;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  before_json: Record<string, unknown>;
  after_json: Record<string, unknown>;
  created_at: string;
};
