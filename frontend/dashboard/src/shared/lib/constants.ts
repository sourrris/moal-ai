export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export const STORAGE_KEYS = {
  token: 'moal_token',
  username: 'moal_username'
} as const;
