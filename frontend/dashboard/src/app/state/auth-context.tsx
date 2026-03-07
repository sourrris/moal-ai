import { createContext, useContext, useMemo, useState } from 'react';

import { STORAGE_KEYS } from '../../shared/lib/constants';

type AuthState = {
  token: string | null;
  username: string | null;
  setSession: (token: string, username: string) => void;
  clearSession: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  const parts = token.split('.');
  if (parts.length < 2) {
    return null;
  }

  try {
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const normalized = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=');
    const payload = JSON.parse(window.atob(normalized));
    return typeof payload === 'object' && payload ? (payload as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function isTenantScopedToken(token: string): boolean {
  const payload = decodeJwtPayload(token);
  if (!payload) {
    return false;
  }

  const subject = payload.sub;
  if (typeof subject !== 'string' || subject.trim().length === 0) {
    return false;
  }

  const tenantId = payload.tenant_id;
  if (typeof tenantId !== 'string' || tenantId.length === 0) {
    return false;
  }

  const roles = payload.roles;
  if (!Array.isArray(roles) || roles.every((role) => typeof role !== 'string' || role.trim().length === 0)) {
    return false;
  }

  const exp = payload.exp;
  if (typeof exp !== 'number') {
    return false;
  }

  return exp * 1000 > Date.now();
}

function clearStoredSession() {
  window.localStorage.removeItem(STORAGE_KEYS.token);
  window.localStorage.removeItem(STORAGE_KEYS.username);
}

function readInitialToken() {
  const storedToken = window.localStorage.getItem(STORAGE_KEYS.token);
  if (!storedToken) {
    return null;
  }

  if (!isTenantScopedToken(storedToken)) {
    clearStoredSession();
    return null;
  }

  return storedToken;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(readInitialToken);
  const [username, setUsername] = useState<string | null>(() => window.localStorage.getItem(STORAGE_KEYS.username));

  const value = useMemo<AuthState>(
    () => ({
      token,
      username,
      setSession: (nextToken: string, nextUsername: string) => {
        if (!isTenantScopedToken(nextToken)) {
          clearStoredSession();
          setToken(null);
          setUsername(null);
          return;
        }
        setToken(nextToken);
        setUsername(nextUsername);
        window.localStorage.setItem(STORAGE_KEYS.token, nextToken);
        window.localStorage.setItem(STORAGE_KEYS.username, nextUsername);
      },
      clearSession: () => {
        setToken(null);
        setUsername(null);
        clearStoredSession();
      }
    }),
    [token, username]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider');
  }
  return context;
}
