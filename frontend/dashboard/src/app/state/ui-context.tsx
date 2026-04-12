import { createContext, useContext, useMemo } from 'react';

type UIState = Record<string, never>;

const UIContext = createContext<UIState | null>(null);

export function UIProvider({ children }: { children: React.ReactNode }) {
  const value = useMemo<UIState>(() => ({}), []);

  return (
    <UIContext.Provider value={value}>
      {children}
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
