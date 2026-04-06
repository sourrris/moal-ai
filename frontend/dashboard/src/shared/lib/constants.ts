export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export const WINDOW_OPTIONS = ['1h', '24h', '7d'] as const;
export type WindowOption = (typeof WINDOW_OPTIONS)[number];

export const STORAGE_KEYS = {
  token: 'moal_token',
  username: 'moal_username',
  window: 'moal_window',
  timezone: 'moal_timezone',
  theme: 'moal_theme',
  density: 'moal_density'
} as const;
