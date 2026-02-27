export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
export const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL ?? 'http://localhost:8020';

export const TENANT_OPTIONS = ['all', 'tenant-alpha', 'tenant-beta'] as const;
export type TenantOption = (typeof TENANT_OPTIONS)[number];

export const WINDOW_OPTIONS = ['1h', '24h', '7d'] as const;
export type WindowOption = (typeof WINDOW_OPTIONS)[number];

export const STORAGE_KEYS = {
  token: 'risk_token',
  username: 'risk_username',
  tenant: 'risk_tenant',
  window: 'risk_window',
  timezone: 'risk_timezone',
  theme: 'risk_theme'
} as const;
