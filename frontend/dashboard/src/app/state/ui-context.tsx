import { createContext, useContext, useMemo, useState } from 'react';

import { STORAGE_KEYS, WINDOW_OPTIONS, type WindowOption } from '../../shared/lib/constants';
import type { TimezonePreference } from '../../shared/lib/time';

type ThemePreference = 'light' | 'dark';
type DensityPreference = 'comfortable' | 'compact';

type UIState = {
  window: WindowOption;
  timezone: TimezonePreference;
  theme: ThemePreference;
  density: DensityPreference;
  setWindow: (value: WindowOption) => void;
  setTimezone: (value: TimezonePreference) => void;
  setTheme: (value: ThemePreference) => void;
  setDensity: (value: DensityPreference) => void;
};

const UIContext = createContext<UIState | null>(null);

function asWindow(input: string | null): WindowOption {
  return WINDOW_OPTIONS.includes((input ?? '') as WindowOption) ? (input as WindowOption) : '24h';
}

function asDensity(input: string | null): DensityPreference {
  if (input === 'compact' || input === 'comfortable') {
    return input;
  }
  if (typeof window !== 'undefined' && window.matchMedia('(min-width: 1280px)').matches) {
    return 'compact';
  }
  return 'comfortable';
}

export function UIProvider({ children }: { children: React.ReactNode }) {
  const [range, setRangeState] = useState<WindowOption>(() => asWindow(window.localStorage.getItem(STORAGE_KEYS.window)));
  const [timezone, setTimezoneState] = useState<TimezonePreference>(
    () => (window.localStorage.getItem(STORAGE_KEYS.timezone) as TimezonePreference | null) ?? 'local'
  );
  const [theme, setThemeState] = useState<ThemePreference>(
    () => (window.localStorage.getItem(STORAGE_KEYS.theme) as ThemePreference | null) ?? 'light'
  );
  const [density, setDensityState] = useState<DensityPreference>(() => asDensity(window.localStorage.getItem(STORAGE_KEYS.density)));

  const value = useMemo<UIState>(
    () => ({
      window: range,
      timezone,
      theme,
      density,
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
      },
      setDensity: (next) => {
        setDensityState(next);
        window.localStorage.setItem(STORAGE_KEYS.density, next);
      }
    }),
    [density, range, theme, timezone]
  );

  return (
    <UIContext.Provider value={value}>
      <div data-theme={theme} data-density={density}>
        {children}
      </div>
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
