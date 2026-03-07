import { describe, expect, it } from 'vitest';

import { deriveSessionState } from './app-state';

function encodeToken(payload: Record<string, unknown>) {
  return `header.${btoa(JSON.stringify(payload))}.signature`;
}

describe('deriveSessionState', () => {
  it('marks malformed saved sessions as invalid', () => {
    const state = deriveSessionState(
      encodeToken({
        tenant_id: 'all',
        scopes: ['control:tenants:read']
      }),
      'ops@example.com'
    );

    expect(state.status).toBe('invalid');
    expect(state.token).toBeNull();
    expect(state.scopes).toEqual([]);
  });

  it('keeps plausible issued sessions ready', () => {
    const state = deriveSessionState(
      encodeToken({
        sub: 'ops@example.com',
        tenant_id: 'tenant-alpha',
        roles: ['admin'],
        scopes: ['control:tenants:read'],
        exp: Math.floor(Date.now() / 1000) + 3600
      }),
      'ops@example.com'
    );

    expect(state.status).toBe('ready');
    expect(state.token).not.toBeNull();
    expect(state.tenantId).toBe('tenant-alpha');
    expect(state.scopes).toEqual(['control:tenants:read']);
  });
});
