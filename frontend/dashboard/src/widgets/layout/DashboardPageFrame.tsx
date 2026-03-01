import { useLocation } from 'react-router-dom';

import { getPageMeta } from '../../app/router/page-meta';
import { cn } from '../../shared/lib/cn';

import { SectionHeader } from '../../shared/ui/SectionHeader';

type DashboardPageFrameProps = {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
  chips?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
};

export function DashboardPageFrame({ children, title, subtitle, chips, actions, className }: DashboardPageFrameProps) {
  const location = useLocation();
  const meta = getPageMeta(location.pathname);

  return (
    <section className={cn('dashboard-frame', className)}>
      <SectionHeader
        title={title ?? meta.title}
        description={subtitle ?? meta.subtitle}
        actions={actions}
        badge={chips}
        className="dashboard-frame-header"
      />
      <div className="stack-lg">{children}</div>
    </section>
  );
}
