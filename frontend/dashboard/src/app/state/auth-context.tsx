import { createContext, useContext, useMemo, useState } from 'react';

import { STORAGE_KEYS } from '../../shared/lib/constants';

type AuthState = {
  token: string | null;
  username: string | null;
  setSession: (token: string, username: string) => void;
  clearSession: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => window.localStorage.getItem(STORAGE_KEYS.token));
  const [username, setUsername] = useState<string | null>(() => window.localStorage.getItem(STORAGE_KEYS.username));

  const value = useMemo<AuthState>(
    () => ({
      token,
      username,
      setSession: (nextToken: string, nextUsername: string) => {
        setToken(nextToken);
        setUsername(nextUsername);
        window.localStorage.setItem(STORAGE_KEYS.token, nextToken);
        window.localStorage.setItem(STORAGE_KEYS.username, nextUsername);
      },
      clearSession: () => {
        setToken(null);
        setUsername(null);
        window.localStorage.removeItem(STORAGE_KEYS.token);
        window.localStorage.removeItem(STORAGE_KEYS.username);
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
