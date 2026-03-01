import { cn } from '../lib/cn';

type KpiCardTrend = 'up' | 'down' | 'neutral';

export type KpiCardProps = {
  label: string;
  value: string;
  meta?: string;
  trend?: KpiCardTrend;
  onClick?: () => void;
  className?: string;
};

const trendClassMap: Record<KpiCardTrend, string> = {
  up: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  down: 'border-red-200 bg-red-50 text-red-700',
  neutral: 'border-zinc-200 bg-zinc-100 text-zinc-700'
};

export function KpiCard({ label, value, meta, trend = 'neutral', onClick, className }: KpiCardProps) {
  const body = (
    <>
      <span className="kpi-card-label" title={label}>
        {label}
      </span>
      <strong className="kpi-card-value">{value}</strong>
      <div className="kpi-card-meta-row">
        {meta ? <span className={cn('kpi-card-meta', trendClassMap[trend])}>{meta}</span> : <span aria-hidden="true" />}
      </div>
    </>
  );

  if (onClick) {
    return (
      <button type="button" className={cn('kpi-card interactive-surface text-left', className)} onClick={onClick}>
        {body}
      </button>
    );
  }

  return <article className={cn('kpi-card', className)}>{body}</article>;
}
