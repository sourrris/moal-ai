import { parseAuthSession, type AuthSession } from './session';

type ConsumedSession = AuthSession & {
  consumed: boolean;
};

export function consumeSessionFromUrl(storage: Storage = window.localStorage): ConsumedSession {
  const url = new URL(window.location.href);
  const token = url.searchParams.get('token');
  const username = url.searchParams.get('username');

  if (!token) {
    return { token: null, username: null, tenantId: null, scopes: [], consumed: false };
  }

  const session = parseAuthSession(token, username);
  if (!session.token) {
    url.searchParams.delete('token');
    url.searchParams.delete('username');
    window.history.replaceState({}, document.title, `${url.pathname}${url.search}${url.hash}`);
    return { token: null, username: null, tenantId: null, scopes: [], consumed: true };
  }

  storage.setItem('risk_token', session.token);
  if (session.username) {
    storage.setItem('risk_username', session.username);
  }

  url.searchParams.delete('token');
  url.searchParams.delete('username');
  window.history.replaceState({}, document.title, `${url.pathname}${url.search}${url.hash}`);

  return { ...session, consumed: true };
}

export function buildMonitoringLoginUrl(baseUrl: string, returnTo: string): string {
  const url = new URL('/login', baseUrl);
  url.searchParams.set('returnTo', returnTo);
  return url.toString();
}
