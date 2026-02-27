export type TimezonePreference = 'local' | 'utc';

export function formatDateTime(iso: string | Date, timezone: TimezonePreference): string {
  const date = typeof iso === 'string' ? new Date(iso) : iso;
  return date.toLocaleString(undefined, {
    hour12: false,
    ...(timezone === 'utc' ? { timeZone: 'UTC', timeZoneName: 'short' } : {})
  });
}

export function toUtcIso(value: Date): string {
  return value.toISOString();
}

export function relativeMinutes(iso: string): number {
  const now = Date.now();
  const value = new Date(iso).getTime();
  return Math.max(0, Math.floor((now - value) / 60000));
}
