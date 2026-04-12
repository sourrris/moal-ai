import { cn } from '../lib/cn';

type SectionHeaderProps = {
  title: string;
  description?: string;
  eyebrow?: string;
  badge?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
};

export function SectionHeader({ title, description, eyebrow, badge, actions, className }: SectionHeaderProps) {
  return (
    <header className={cn('section-header', className)}>
      <div className="section-header-copy">
        {eyebrow ? <span className="section-header-eyebrow">{eyebrow}</span> : null}
        <h2 className="section-header-title">{title}</h2>
        {description && <p className="section-header-description">{description}</p>}
        {badge ? <div className="section-header-badges">{badge}</div> : null}
      </div>
      {actions && <div className="inline-actions">{actions}</div>}
    </header>
  );
}
