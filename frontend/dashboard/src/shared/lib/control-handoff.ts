export function buildConsoleHandoffUrl(baseUrl: string, token: string, username: string | null): string {
  const url = new URL(baseUrl, window.location.origin);
  url.searchParams.set('token', token);
  if (username) {
    url.searchParams.set('username', username);
  }
  return url.toString();
}

export function buildMonitoringLoginUrl(baseUrl: string, returnTo: string): string {
  const url = new URL('/login', baseUrl);
  url.searchParams.set('returnTo', returnTo);
  return url.toString();
}
