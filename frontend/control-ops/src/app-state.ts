import { consumeSessionFromUrl } from '../../packages/control-auth/src/handoff';
import { parseAuthSession } from '../../packages/control-auth/src/session';

export const DEFAULT_LIMIT = 100;
export const MIN_LIMIT = 1;
export const MAX_LIMIT = 500;

export type SessionStatus = 'missing' | 'invalid' | 'ready';

export type SessionState = {
  status: SessionStatus;
  token: string | null;
  username: string | null;
  tenantId: string;
  scopes: string[];
};

export function deriveSessionState(token: string | null, username: string | null): SessionState {
  if (!token) {
    return {
      status: 'missing',
      token: null,
      username: null,
      tenantId: 'all',
      scopes: []
    };
  }

  const session = parseAuthSession(token, username);
  if (!session.token) {
    return {
      status: 'invalid',
      token: null,
      username: username ?? null,
      tenantId: 'all',
      scopes: []
    };
  }

  return {
    status: 'ready',
    token: session.token,
    username: session.username,
    tenantId: session.tenantId ?? 'all',
    scopes: session.scopes
  };
}

export function readHandedOffSession(): SessionState | null {
  const session = consumeSessionFromUrl();
  if (!session.token) {
    return null;
  }

  return {
    status: 'ready',
    token: session.token,
    username: session.username,
    tenantId: session.tenantId ?? 'all',
    scopes: session.scopes
  };
}

export function hasAllScopes(scopes: string[], requiredScopes: string[]): boolean {
  return requiredScopes.every((scope) => scopes.includes(scope));
}

export function hasAnyScope(scopes: string[], requiredScopes: string[]): boolean {
  return requiredScopes.some((scope) => scopes.includes(scope));
}

export function normalizeLimit(value: string | number, fallback = DEFAULT_LIMIT): number {
  const parsed = typeof value === 'number' ? value : Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(MAX_LIMIT, Math.max(MIN_LIMIT, parsed));
}
