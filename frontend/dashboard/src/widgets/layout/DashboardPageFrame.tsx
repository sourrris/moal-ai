import { cn } from '../../shared/lib/cn';

import { SectionHeader } from '../../shared/ui/SectionHeader';

type DashboardPageFrameProps = {
  children: React.ReactNode;
  eyebrow?: string;
  title?: string;
  subtitle?: string;
  chips?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
};

export function DashboardPageFrame({
  children,
  eyebrow,
  title,
  subtitle,
  chips,
  actions,
  className
}: DashboardPageFrameProps) {
  return (
    <section className={cn('dashboard-frame', className)}>
      {(title || subtitle) && (
        <SectionHeader
          eyebrow={eyebrow}
          title={title ?? 'Dashboard'}
          description={subtitle ?? 'User behavior analytics overview'}
          actions={actions}
          badge={chips}
          className="dashboard-frame-header"
        />
      )}
      <div className="stack-lg">{children}</div>
    </section>
  );
}
