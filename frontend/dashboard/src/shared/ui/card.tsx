import { cn } from '../lib/cn';

export function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return <section className={cn('ui-card', className)}>{children}</section>;
}
