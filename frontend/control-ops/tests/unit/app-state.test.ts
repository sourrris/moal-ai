import { describe, expect, it } from 'vitest';

import {
  DEFAULT_LIMIT,
  deriveSessionState,
  hasAllScopes,
  hasAnyScope,
  normalizeLimit
} from '../../src/app-state';

function createJwt(payload: Record<string, unknown>): string {
  const json = JSON.stringify(payload);
  const encoded = globalThis.btoa(json).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  return `header.${encoded}.signature`;
}

describe('deriveSessionState', () => {
  it('returns missing when no token is present', () => {
    expect(deriveSessionState(null, null)).toEqual({
      status: 'missing',
      token: null,
      username: null,
      tenantId: 'all',
      scopes: []
    });
  });

  it('returns invalid when token cannot be decoded as a JWT payload', () => {
    expect(deriveSessionState('not-a-jwt', 'ops@example.com')).toEqual({
      status: 'invalid',
      token: null,
      username: 'ops@example.com',
      tenantId: 'all',
      scopes: []
    });
  });

  it('returns ready for a valid JWT payload', () => {
    const token = createJwt({
      sub: 'ops@example.com',
      tenant_id: 'tenant-alpha',
      roles: ['admin'],
      scopes: ['control:tenants:read', 'control:config:write'],
      exp: Math.floor(Date.now() / 1000) + 3600
    });

    expect(deriveSessionState(token, 'ops@example.com')).toEqual({
      status: 'ready',
      token,
      username: 'ops@example.com',
      tenantId: 'tenant-alpha',
      scopes: ['control:tenants:read', 'control:config:write']
    });
  });
});

describe('scope helpers', () => {
  it('checks all required scopes', () => {
    expect(hasAllScopes(['a', 'b'], ['a'])).toBe(true);
    expect(hasAllScopes(['a'], ['a', 'b'])).toBe(false);
  });

  it('checks any required scope', () => {
    expect(hasAnyScope(['a', 'b'], ['c', 'b'])).toBe(true);
    expect(hasAnyScope(['a'], ['b', 'c'])).toBe(false);
  });
});

describe('normalizeLimit', () => {
  it('uses the fallback for invalid values', () => {
    expect(normalizeLimit('')).toBe(DEFAULT_LIMIT);
    expect(normalizeLimit('abc')).toBe(DEFAULT_LIMIT);
  });

  it('clamps below and above the allowed range', () => {
    expect(normalizeLimit('0')).toBe(1);
    expect(normalizeLimit('999')).toBe(500);
  });

  it('keeps valid in-range values', () => {
    expect(normalizeLimit('42')).toBe(42);
  });
});
