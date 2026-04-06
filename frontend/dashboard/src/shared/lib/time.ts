export type TimezonePreference = 'local' | 'utc';

export function formatDateTime(iso: string | Date, timezone: TimezonePreference): string {
  const date = typeof iso === 'string' ? new Date(iso) : iso;
  return date.toLocaleString(undefined, {
    hour12: false,
    ...(timezone === 'utc' ? { timeZone: 'UTC', timeZoneName: 'short' } : {})
  });
}

