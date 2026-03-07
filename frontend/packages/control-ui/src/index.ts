export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type BadgeVariant = 'neutral' | 'info' | 'success' | 'warning' | 'critical';
export type StatusVariant = 'info' | 'success' | 'warning' | 'error';

export function cn(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(' ');
}

export function buttonClassName(variant: ButtonVariant = 'secondary', className?: string) {
  return cn('control-button', `control-button--${variant}`, className);
}

export function badgeClassName(variant: BadgeVariant = 'neutral', className?: string) {
  return cn('control-badge', `control-badge--${variant}`, className);
}

export function statusBannerClassName(variant: StatusVariant = 'info', className?: string) {
  return cn('control-banner', `control-banner--${variant}`, className);
}
