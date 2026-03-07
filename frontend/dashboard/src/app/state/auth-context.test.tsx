import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { AuthProvider, useAuth } from './auth-context';

function encodeToken(payload: Record<string, unknown>) {
  return `header.${btoa(JSON.stringify(payload))}.signature`;
}

function Probe() {
  const { token, username } = useAuth();
  return (
    <div>
      <span data-testid="token">{token ?? 'none'}</span>
      <span data-testid="username">{username ?? 'none'}</span>
    </div>
  );
}

describe('AuthProvider', () => {
  let storage: Storage;

  beforeEach(() => {
    const values = new Map<string, string>();
    storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value);
      },
      removeItem: (key: string) => {
        values.delete(key);
      },
      clear: () => {
        values.clear();
      },
      key: (index: number) => Array.from(values.keys())[index] ?? null,
      get length() {
        return values.size;
      }
    };

    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: storage
    });
  });

  afterEach(() => {
    storage.clear();
  });

  it('clears malformed stored sessions during bootstrap', () => {
    window.localStorage.setItem('risk_token', encodeToken({ tenant_id: 'tenant-alpha' }));
    window.localStorage.setItem('risk_username', 'ops@example.com');

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    expect(screen.getByTestId('token')).toHaveTextContent('none');
    expect(screen.getByTestId('username')).toHaveTextContent('none');
    expect(window.localStorage.getItem('risk_token')).toBeNull();
    expect(window.localStorage.getItem('risk_username')).toBeNull();
  });

  it('keeps issued-looking sessions available', () => {
    window.localStorage.setItem(
      'risk_token',
      encodeToken({
        sub: 'analyst@example.com',
        tenant_id: 'tenant-alpha',
        roles: ['admin'],
        exp: Math.floor(Date.now() / 1000) + 3600
      })
    );
    window.localStorage.setItem('risk_username', 'analyst@example.com');

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    expect(screen.getByTestId('token')).not.toHaveTextContent('none');
    expect(screen.getByTestId('username')).toHaveTextContent('analyst@example.com');
  });
});
