import type {
  ButtonHTMLAttributes,
  CSSProperties,
  HTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes
} from 'react';
import { useEffect, useId, useRef, useState } from 'react';

import {
  badgeClassName,
  buttonClassName,
  cn,
  statusBannerClassName,
  type BadgeVariant,
  type ButtonVariant,
  type StatusVariant
} from '../../packages/control-ui/src';

export { badgeClassName, buttonClassName, cn };

export function Button({
  variant = 'secondary',
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return <button className={buttonClassName(variant, className)} {...props} />;
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn('control-input', className)} {...props} />;
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn('control-select', className)} {...props} />;
}

export function TextArea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn('control-textarea', className)} {...props} />;
}

export function Badge({
  children,
  variant = 'neutral',
  className
}: {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
}) {
  return <span className={badgeClassName(variant, className)}>{children}</span>;
}

type SectionHeaderProps = {
  title: string;
  description?: string;
  badge?: ReactNode;
  actions?: ReactNode;
  className?: string;
};

function SectionHeader({ title, description, badge, actions, className }: SectionHeaderProps) {
  return (
    <header className={cn('control-section-header', className)}>
      <div className="control-section-header__copy">
        <div className="control-section-header__title-row">
          <h2 className="control-section-header__title">{title}</h2>
          {badge}
        </div>
        {description ? <p className="control-section-header__description">{description}</p> : null}
      </div>
      {actions ? <div className="control-inline-actions">{actions}</div> : null}
    </header>
  );
}

export function DataPanel({
  title,
  description,
  badge,
  actions,
  className,
  children
}: SectionHeaderProps & { children: ReactNode }) {
  return (
    <section className={cn('control-panel', className)}>
      <SectionHeader title={title} description={description} badge={badge} actions={actions} />
      <div className="control-panel__body">{children}</div>
    </section>
  );
}

export function ConsolePageFrame({
  title,
  subtitle,
  chips,
  actions,
  className,
  children
}: {
  title: string;
  subtitle?: string;
  chips?: ReactNode;
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={cn('control-page-frame', className)}>
      <SectionHeader
        title={title}
        description={subtitle}
        badge={chips}
        actions={actions}
        className="control-page-frame__header"
      />
      <div className="control-page-frame__body">{children}</div>
    </section>
  );
}

export function MetricCard({
  label,
  value,
  meta,
  className
}: {
  label: string;
  value: string;
  meta?: string;
  className?: string;
}) {
  return (
    <article className={cn('control-metric-card', className)}>
      <span className="control-metric-card__label">{label}</span>
      <strong className="control-metric-card__value">{value}</strong>
      <span className="control-metric-card__meta">{meta ?? '\u00A0'}</span>
    </article>
  );
}

export function DetailList({ className, children }: { className?: string; children: ReactNode }) {
  return <dl className={cn('control-detail-list', className)}>{children}</dl>;
}

export function DetailItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="control-detail-item">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

export function StatusBanner({
  variant = 'info',
  className,
  children,
  ...props
}: {
  variant?: StatusVariant;
  className?: string;
  children: ReactNode;
} & HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={statusBannerClassName(variant, className)} {...props}>
      {children}
    </div>
  );
}

export function QueryStatus({
  state,
  subject,
  error
}: {
  state: 'loading' | 'error' | 'empty';
  subject: string;
  error?: string;
}) {
  const message =
    state === 'loading'
      ? `Loading ${subject}.`
      : state === 'empty'
        ? `No ${subject} available yet.`
        : `Unable to load ${subject}.`;

  return (
    <div aria-live="polite" className="control-query-state" data-testid={`${subject.replace(/\s+/g, '-').toLowerCase()}-${state}`}>
      <p>{message}</p>
      {state === 'error' && error ? <p className="control-query-state__error">{error}</p> : null}
    </div>
  );
}

export function ScopeGate({
  allowed,
  title,
  message,
  children
}: {
  allowed: boolean;
  title: string;
  message: string;
  children: ReactNode;
}) {
  if (allowed) {
    return <>{children}</>;
  }

  return (
    <DataPanel title={title} badge={<Badge variant="warning">Restricted</Badge>}>
      <p data-testid="scope-gate-message" className="muted">
        {message}
      </p>
    </DataPanel>
  );
}

export type DensityMode = 'comfortable' | 'compact';

export function useDensityPreference(storageKey: string) {
  const [density, setDensity] = useState<DensityMode>(() => {
    if (typeof window === 'undefined') {
      return 'comfortable';
    }
    const stored = window.localStorage.getItem(storageKey);
    return stored === 'compact' ? 'compact' : 'comfortable';
  });

  useEffect(() => {
    if (typeof document === 'undefined') {
      return;
    }
    document.documentElement.dataset.density = density;
    window.localStorage.setItem(storageKey, density);
  }, [density, storageKey]);

  return [density, setDensity] as const;
}

export function DensityToggle({
  value,
  onChange,
  className
}: {
  value: DensityMode;
  onChange: (value: DensityMode) => void;
  className?: string;
}) {
  return (
    <div className={cn('control-density-toggle', className)} role="group" aria-label="Display density">
      {(['comfortable', 'compact'] as const).map((option) => (
        <button
          key={option}
          type="button"
          className={cn(
            'control-density-toggle__button',
            value === option && 'control-density-toggle__button--active'
          )}
          onClick={() => onChange(option)}
        >
          {option === 'comfortable' ? 'Comfortable' : 'Compact'}
        </button>
      ))}
    </div>
  );
}

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

function AmbientBackground() {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const id = useId().replace(/:/g, '');
  const patternId = `control-ambient-grid-${id}`;

  useEffect(() => {
    const root = rootRef.current;
    if (!root) {
      return;
    }

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let targetX = 50;
    let targetY = 18;
    let currentX = 50;
    let currentY = 18;
    let targetIntensity = 0.58;
    let currentIntensity = targetIntensity;
    let raf = 0;
    let idleTimer: number | null = null;

    const apply = () => {
      root.style.setProperty('--control-ambient-x', `${currentX.toFixed(2)}%`);
      root.style.setProperty('--control-ambient-y', `${currentY.toFixed(2)}%`);
      root.style.setProperty('--control-ambient-intensity', currentIntensity.toFixed(3));
    };

    const resetTarget = () => {
      targetX = 50;
      targetY = 18;
      targetIntensity = 0.48;
    };

    const setIdle = () => {
      if (idleTimer) {
        window.clearTimeout(idleTimer);
      }
      idleTimer = window.setTimeout(() => {
        targetIntensity = 0.52;
      }, 120);
    };

    const updateTarget = (clientX: number, clientY: number) => {
      const rect = root.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) {
        return;
      }
      targetX = clamp(((clientX - rect.left) / rect.width) * 100, 0, 100);
      targetY = clamp(((clientY - rect.top) / rect.height) * 100, 0, 100);
      targetIntensity = 0.92;
      setIdle();
    };

    const animate = () => {
      currentX += (targetX - currentX) * 0.1;
      currentY += (targetY - currentY) * 0.1;
      currentIntensity += (targetIntensity - currentIntensity) * 0.16;
      apply();
      raf = window.requestAnimationFrame(animate);
    };

    if (reduceMotion.matches) {
      apply();
      return;
    }

    const handlePointerMove = (event: PointerEvent) => {
      if (event.pointerType === 'touch') {
        return;
      }
      updateTarget(event.clientX, event.clientY);
    };

    const handleTouchMove = (event: TouchEvent) => {
      const touch = event.touches[0];
      if (touch) {
        updateTarget(touch.clientX, touch.clientY);
      }
    };

    const handleMouseOut = (event: MouseEvent) => {
      if (!event.relatedTarget) {
        resetTarget();
      }
    };

    const handleVisibilityChange = () => {
      if (document.hidden) {
        resetTarget();
      }
    };

    apply();
    raf = window.requestAnimationFrame(animate);
    window.addEventListener('pointermove', handlePointerMove, { passive: true });
    window.addEventListener('touchmove', handleTouchMove, { passive: true });
    window.addEventListener('mouseout', handleMouseOut, { passive: true });
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.cancelAnimationFrame(raf);
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('touchmove', handleTouchMove);
      window.removeEventListener('mouseout', handleMouseOut);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      if (idleTimer) {
        window.clearTimeout(idleTimer);
      }
    };
  }, []);

  return (
    <div
      ref={rootRef}
      aria-hidden="true"
      className="control-ambient"
      style={
        {
          ['--control-ambient-x' as string]: '50%',
          ['--control-ambient-y' as string]: '18%',
          ['--control-ambient-intensity' as string]: '0.58'
        } as CSSProperties
      }
    >
      <div className="control-ambient__base" />
      <div className="control-ambient__wash" />
      <div className="control-ambient__spotlight" />
      <svg className="control-ambient__grid" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id={patternId} width="26" height="26" patternUnits="userSpaceOnUse">
            <circle cx="2" cy="2" r="1" fill="#a1a1aa" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill={`url(#${patternId})`} />
      </svg>
    </div>
  );
}

export function ControlShell({
  brand,
  navigation,
  actions,
  utilityBar,
  children
}: {
  brand: ReactNode;
  navigation?: ReactNode;
  actions?: ReactNode;
  utilityBar?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="control-shell">
      <AmbientBackground />
      <div className="control-shell__layer">
        <header className="control-shell__topbar">
          <div className="control-shell__topbar-inner">
            {brand}
            {navigation ? <div className="control-shell__desktop-nav">{navigation}</div> : null}
            {actions ? <div className="control-shell__actions">{actions}</div> : null}
          </div>
          {navigation ? <div className="control-shell__mobile-row">{navigation}</div> : null}
        </header>

        {utilityBar ? (
          <section className="control-shell__utility-shell">
            <div className="control-shell__utility">{utilityBar}</div>
          </section>
        ) : null}

        <div className="control-shell__main">
          <main className="control-shell__content">{children}</main>
        </div>
      </div>
    </div>
  );
}
