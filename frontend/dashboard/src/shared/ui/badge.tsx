import { cn } from '../lib/cn';

type BadgeVariant = 'neutral' | 'info' | 'success' | 'warning' | 'critical';

const variantClassMap: Record<BadgeVariant, string> = {
  neutral: 'ui-badge--neutral',
  info: 'ui-badge--info',
  success: 'ui-badge--success',
  warning: 'ui-badge--warning',
  critical: 'ui-badge--critical'
};

export function Badge({
  children,
  variant = 'neutral',
  className
}: {
  children: React.ReactNode;
  variant?: BadgeVariant;
  className?: string;
}) {
  return <span className={cn('ui-badge', variantClassMap[variant], className)}>{children}</span>;
}
