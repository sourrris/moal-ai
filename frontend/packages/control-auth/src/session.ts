export type AuthSession = {
  token: string | null;
  username: string | null;
  tenantId: string | null;
  scopes: string[];
};

function decodePayload(token: string): Record<string, unknown> | null {
  const parts = token.split('.');
  if (parts.length < 2) {
    return null;
  }

  try {
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const normalized = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=');
    const decoder = typeof globalThis.atob === 'function' ? globalThis.atob : null;
    if (!decoder) {
      return null;
    }
    const payload = JSON.parse(decoder(normalized));
    if (typeof payload !== 'object' || payload === null) {
      return null;
    }
    return payload as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function parseAuthSession(token: string | null, username: string | null): AuthSession {
  if (!token) {
    return { token: null, username: null, tenantId: null, scopes: [] };
  }

  const payload = decodePayload(token);
  if (!payload) {
    return { token: null, username: null, tenantId: null, scopes: [] };
  }
  const subject = typeof payload?.sub === 'string' ? payload.sub.trim() : '';
  const tenantId = typeof payload?.tenant_id === 'string' ? payload.tenant_id.trim() : null;
  const roles = Array.isArray(payload?.roles) ? payload.roles.filter((item): item is string => typeof item === 'string') : [];
  const exp = typeof payload?.exp === 'number' ? payload.exp : null;
  const scopes = Array.isArray(payload?.scopes) ? payload.scopes.filter((s): s is string => typeof s === 'string') : [];

  if (!subject || !tenantId || !exp || exp * 1000 <= Date.now() || roles.length === 0) {
    return { token: null, username: null, tenantId: null, scopes: [] };
  }

  return {
    token,
    username: username ?? subject,
    tenantId,
    scopes
  };
}

export function hasScope(session: AuthSession, scope: string): boolean {
  return session.scopes.includes(scope);
}
