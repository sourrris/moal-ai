import type { ReactNode } from 'react';

export function OpsShell({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <div
      style={{
        minHeight: '100vh',
        background:
          'radial-gradient(circle at top right, rgba(14,116,144,0.08), transparent 48%), linear-gradient(180deg,#f8fafc,#f1f5f9)',
        color: '#0f172a'
      }}
    >
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '18px 26px',
          borderBottom: '1px solid #cbd5e1',
          background: 'rgba(248,250,252,0.94)',
          position: 'sticky',
          top: 0,
          backdropFilter: 'blur(6px)',
          zIndex: 1
        }}
      >
        <h1 style={{ margin: 0, fontSize: 24 }}>Aegis Ops Cockpit · {title}</h1>
        <div>{actions}</div>
      </header>
      <main style={{ padding: 22 }}>{children}</main>
    </div>
  );
}

export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section
      style={{
        background: '#ffffff',
        border: '1px solid #dbe3ef',
        borderRadius: 12,
        padding: 14,
        marginBottom: 14
      }}
    >
      <h2 style={{ margin: '0 0 10px 0', fontSize: 17 }}>{title}</h2>
      {children}
    </section>
  );
}

export function Badge({ value }: { value: string }) {
  return (
    <span
      style={{
        display: 'inline-block',
        fontSize: 12,
        padding: '2px 8px',
        borderRadius: 999,
        border: '1px solid #94a3b8',
        marginLeft: 8
      }}
    >
      {value}
    </span>
  );
}
