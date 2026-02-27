import { createContext, useContext, useMemo, useState } from 'react';

import { STORAGE_KEYS, TENANT_OPTIONS, WINDOW_OPTIONS, type TenantOption, type WindowOption } from '../../shared/lib/constants';
import type { TimezonePreference } from '../../shared/lib/time';

type ThemePreference = 'light' | 'dark';

type UIState = {
  tenant: TenantOption;
  window: WindowOption;
  timezone: TimezonePreference;
  theme: ThemePreference;
  setTenant: (value: TenantOption) => void;
  setWindow: (value: WindowOption) => void;
  setTimezone: (value: TimezonePreference) => void;
  setTheme: (value: ThemePreference) => void;
};

const UIContext = createContext<UIState | null>(null);

function asTenant(input: string | null): TenantOption {
  return TENANT_OPTIONS.includes((input ?? '') as TenantOption) ? (input as TenantOption) : 'all';
}

function asWindow(input: string | null): WindowOption {
  return WINDOW_OPTIONS.includes((input ?? '') as WindowOption) ? (input as WindowOption) : '24h';
}

export function UIProvider({ children }: { children: React.ReactNode }) {
  const [tenant, setTenantState] = useState<TenantOption>(() => asTenant(window.localStorage.getItem(STORAGE_KEYS.tenant)));
  const [range, setRangeState] = useState<WindowOption>(() => asWindow(window.localStorage.getItem(STORAGE_KEYS.window)));
  const [timezone, setTimezoneState] = useState<TimezonePreference>(
    () => (window.localStorage.getItem(STORAGE_KEYS.timezone) as TimezonePreference | null) ?? 'local'
  );
  const [theme, setThemeState] = useState<ThemePreference>(
    () => (window.localStorage.getItem(STORAGE_KEYS.theme) as ThemePreference | null) ?? 'light'
  );

  const value = useMemo<UIState>(
    () => ({
      tenant,
      window: range,
      timezone,
      theme,
      setTenant: (next) => {
        setTenantState(next);
        window.localStorage.setItem(STORAGE_KEYS.tenant, next);
      },
      setWindow: (next) => {
        setRangeState(next);
        window.localStorage.setItem(STORAGE_KEYS.window, next);
      },
      setTimezone: (next) => {
        setTimezoneState(next);
        window.localStorage.setItem(STORAGE_KEYS.timezone, next);
      },
      setTheme: (next) => {
        setThemeState(next);
        window.localStorage.setItem(STORAGE_KEYS.theme, next);
      }
    }),
    [range, tenant, theme, timezone]
  );

  return (
    <UIContext.Provider value={value}>
      <div data-theme={theme}>{children}</div>
    </UIContext.Provider>
  );
}

export function useUI() {
  const context = useContext(UIContext);
  if (!context) {
    throw new Error('useUI must be used inside UIProvider');
  }
  return context;
}
