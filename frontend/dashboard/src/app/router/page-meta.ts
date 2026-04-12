export type PageMeta = {
  title: string;
  subtitle: string;
};

export const PAGE_META: PageMeta = {
  title: 'Dashboard',
  subtitle: 'User behavior analytics — events, alerts, and anomaly signals at a glance.',
};

export function getPageMeta(): PageMeta {
  return PAGE_META;
}