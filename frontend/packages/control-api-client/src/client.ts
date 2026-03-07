import type {
  AlertDestinationDTO,
  ConfigAuditItemDTO,
  ConnectorCatalogItem,
  ConnectorRunNowResponse,
  DeliveryLogItemDTO,
  ReconciliationSummaryDTO,
  TenantCreateRequest,
  TenantConfigurationDTO,
  TenantSummary,
  TenantUpdateRequest
} from './types';

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  token?: string;
};

async function requestJson<T>(baseUrl: string, path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    method: options.method ?? 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {})
    },
    body: options.body ? JSON.stringify(options.body) : undefined
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Request failed (${response.status}): ${detail || response.statusText}`);
  }

  return response.json() as Promise<T>;
}

export class ControlApiClient {
  constructor(private readonly baseUrl: string, private readonly token: string) {}

  listTenants(): Promise<TenantSummary[]> {
    return requestJson(this.baseUrl, '/control/v1/tenants', { token: this.token });
  }

  getTenant(tenantId: string): Promise<TenantSummary> {
    return requestJson(this.baseUrl, `/control/v1/tenants/${tenantId}`, { token: this.token });
  }

  createTenant(payload: TenantCreateRequest): Promise<TenantSummary> {
    return requestJson(this.baseUrl, '/control/v1/tenants', {
      method: 'POST',
      token: this.token,
      body: payload
    });
  }

  updateTenant(tenantId: string, payload: TenantUpdateRequest): Promise<TenantSummary> {
    return requestJson(this.baseUrl, `/control/v1/tenants/${tenantId}`, {
      method: 'PATCH',
      token: this.token,
      body: payload
    });
  }

  assignTenantAdmin(tenantId: string, payload: { username: string; role_name?: string }): Promise<Record<string, unknown>> {
    return requestJson(this.baseUrl, `/control/v1/tenants/${tenantId}/admins`, {
      method: 'POST',
      token: this.token,
      body: payload
    });
  }

  getTenantConfiguration(tenantId: string): Promise<TenantConfigurationDTO> {
    return requestJson(this.baseUrl, `/control/v1/tenants/${tenantId}/configuration`, { token: this.token });
  }

  updateTenantConfiguration(
    tenantId: string,
    payload: Partial<Pick<TenantConfigurationDTO, 'anomaly_threshold' | 'enabled_connectors' | 'model_version' | 'rule_overrides_json'>> & {
      expected_version?: number;
    }
  ): Promise<TenantConfigurationDTO> {
    return requestJson(this.baseUrl, `/control/v1/tenants/${tenantId}/configuration`, {
      method: 'PUT',
      token: this.token,
      body: payload
    });
  }

  listConnectorsCatalog(): Promise<ConnectorCatalogItem[]> {
    return requestJson(this.baseUrl, '/control/v1/connectors/catalog', { token: this.token });
  }

  runConnectorNow(sourceName: string): Promise<ConnectorRunNowResponse> {
    return requestJson(this.baseUrl, `/control/v1/connectors/${sourceName}/run-now`, {
      method: 'POST',
      token: this.token
    });
  }

  globalEnableConnector(sourceName: string): Promise<{ status: string; source_name: string; enabled: boolean }> {
    return requestJson(this.baseUrl, `/control/v1/connectors/${sourceName}/global-enable`, {
      method: 'POST',
      token: this.token
    });
  }

  globalDisableConnector(sourceName: string): Promise<{ status: string; source_name: string; enabled: boolean }> {
    return requestJson(this.baseUrl, `/control/v1/connectors/${sourceName}/global-disable`, {
      method: 'POST',
      token: this.token
    });
  }

  listAlertDestinations(tenantId: string): Promise<AlertDestinationDTO[]> {
    return requestJson(this.baseUrl, `/control/v1/tenants/${tenantId}/alert-destinations`, { token: this.token });
  }

  createAlertDestination(
    tenantId: string,
    payload: {
      channel: 'webhook' | 'email' | 'slack';
      name: string;
      enabled: boolean;
      config: Record<string, unknown>;
    }
  ): Promise<AlertDestinationDTO> {
    return requestJson(this.baseUrl, `/control/v1/tenants/${tenantId}/alert-destinations`, {
      method: 'POST',
      token: this.token,
      body: payload
    });
  }

  verifyAlertDestination(tenantId: string, destinationId: string): Promise<AlertDestinationDTO> {
    return requestJson(this.baseUrl, `/control/v1/tenants/${tenantId}/alert-destinations/${destinationId}/verify`, {
      method: 'POST',
      token: this.token
    });
  }

  getIngestionReconciliation(tenantId: string): Promise<ReconciliationSummaryDTO> {
    return requestJson(this.baseUrl, `/control/v1/tenants/${tenantId}/reconciliation/ingestion`, {
      token: this.token
    });
  }

  listDeliveryLogs(params: { tenant_id?: string; limit?: number } = {}): Promise<DeliveryLogItemDTO[]> {
    const query = new URLSearchParams();
    if (params.tenant_id) {
      query.set('tenant_id', params.tenant_id);
    }
    if (typeof params.limit === 'number') {
      query.set('limit', String(params.limit));
    }
    const suffix = query.size > 0 ? `?${query.toString()}` : '';
    return requestJson(this.baseUrl, `/control/v1/delivery/logs${suffix}`, { token: this.token });
  }

  listAuditConfigChanges(params: { tenant_id?: string; limit?: number } = {}): Promise<ConfigAuditItemDTO[]> {
    const query = new URLSearchParams();
    if (params.tenant_id) {
      query.set('tenant_id', params.tenant_id);
    }
    if (typeof params.limit === 'number') {
      query.set('limit', String(params.limit));
    }
    const suffix = query.size > 0 ? `?${query.toString()}` : '';
    return requestJson(this.baseUrl, `/control/v1/audit/config-changes${suffix}`, { token: this.token });
  }
}
