import { Card } from './card';
import { cn } from '../lib/cn';

import { SectionHeader } from './SectionHeader';

type DataPanelProps = {
  title: string;
  description?: string;
  badge?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
};

export function DataPanel({ title, description, badge, actions, children, className }: DataPanelProps) {
  return (
    <Card className={cn('data-panel', className)}>
      <SectionHeader title={title} description={description} badge={badge} actions={actions} />
      {children}
    </Card>
  );
}
