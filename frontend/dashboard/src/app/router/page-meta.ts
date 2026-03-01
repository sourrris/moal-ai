export type PageMeta = {
  title: string;
  subtitle: string;
  primaryAction?: 'ingest' | 'none';
};

export const PAGE_META_BY_ROUTE: Record<string, PageMeta> = {
  '/overview': {
    title: 'Overview',
    subtitle: 'Live operational posture, anomaly trends, and connector health in one place.',
    primaryAction: 'ingest'
  },
  '/alerts': {
    title: 'Alerts',
    subtitle: 'Filter, triage, and investigate anomalies with realtime stream context.',
    primaryAction: 'none'
  },
  '/events': {
    title: 'Events',
    subtitle: 'Inspect ingestion lifecycle events and internet source update activity.',
    primaryAction: 'none'
  },
  '/models': {
    title: 'Models',
    subtitle: 'Track serving versions, threshold behavior, and training actions.',
    primaryAction: 'none'
  },
  '/settings': {
    title: 'Settings',
    subtitle: 'Manage workspace preferences and runtime diagnostics.',
    primaryAction: 'none'
  }
};

const DEFAULT_PAGE_META: PageMeta = {
  title: 'Overview',
  subtitle: 'Live operational posture, anomaly trends, and connector health in one place.',
  primaryAction: 'ingest'
};

export function getPageMeta(pathname: string): PageMeta {
  const match = Object.entries(PAGE_META_BY_ROUTE).find(([route]) => pathname.startsWith(route));
  return match ? match[1] : DEFAULT_PAGE_META;
}
