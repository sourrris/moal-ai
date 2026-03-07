import type { ReactNode } from 'react';

export function AppShell({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <div style={{ minHeight: '100vh', background: 'linear-gradient(135deg,#f7f9fc,#eef4ff)', color: '#0f172a' }}>
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '20px 28px',
          borderBottom: '1px solid #dbe7ff',
          background: 'rgba(255,255,255,0.9)',
          position: 'sticky',
          top: 0,
          backdropFilter: 'blur(6px)'
        }}
      >
        <h1 style={{ margin: 0, fontSize: 24, letterSpacing: 0.2 }}>{title}</h1>
        <div>{actions}</div>
      </header>
      <main style={{ padding: 24 }}>{children}</main>
    </div>
  );
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section
      style={{
        background: '#ffffff',
        border: '1px solid #dde7ff',
        borderRadius: 14,
        padding: 16,
        marginBottom: 16,
        boxShadow: '0 8px 24px rgba(15,23,42,0.06)'
      }}
    >
      <h2 style={{ margin: '0 0 12px 0', fontSize: 18 }}>{title}</h2>
      {children}
    </section>
  );
}

export function KeyValue({ label, value }: { label: string; value: ReactNode }) {
  return (
    <p style={{ margin: '6px 0' }}>
      <strong>{label}</strong>: {value}
    </p>
  );
}
