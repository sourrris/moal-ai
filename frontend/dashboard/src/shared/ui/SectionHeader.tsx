import { cn } from '../lib/cn';

type SectionHeaderProps = {
  title: string;
  description?: string;
  badge?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
};

export function SectionHeader({ title, description, badge, actions, className }: SectionHeaderProps) {
  return (
    <header className={cn('section-header', className)}>
      <div className="section-header-copy">
        <div className="inline-flex items-center gap-2">
          <h2 className="section-header-title">{title}</h2>
          {badge}
        </div>
        {description && <p className="section-header-description">{description}</p>}
      </div>
      {actions && <div className="inline-actions">{actions}</div>}
    </header>
  );
}
