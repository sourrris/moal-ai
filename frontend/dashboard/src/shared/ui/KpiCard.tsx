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
  up: 'kpi-card-meta--up',
  down: 'kpi-card-meta--down',
  neutral: 'kpi-card-meta--neutral'
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
