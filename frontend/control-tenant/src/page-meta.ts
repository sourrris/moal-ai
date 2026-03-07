export type TenantPageMeta = {
  path: string;
  label: string;
  title: string;
  subtitle: string;
};

export const TENANT_PAGE_META: TenantPageMeta[] = [
  {
    path: '/workspace/overview',
    label: 'Overview',
    title: 'Workspace Overview',
    subtitle: 'Tenant posture, connector coverage, and reconciliation state in a single operating view.'
  },
  {
    path: '/workspace/config/connectors',
    label: 'Connectors',
    title: 'Connector Policy',
    subtitle: 'Control which shared intelligence feeds are enabled for this tenant workspace.'
  },
  {
    path: '/workspace/config/risk-policy',
    label: 'Risk Policy',
    title: 'Risk Policy',
    subtitle: 'Tune anomaly thresholds and tenant-specific rule overrides without leaving the console.'
  },
  {
    path: '/workspace/config/model-policy',
    label: 'Model Policy',
    title: 'Model Policy',
    subtitle: 'Pin or release tenant model versions while preserving the current serving workflow.'
  },
  {
    path: '/workspace/test-lab',
    label: 'Test Lab',
    title: 'Test Lab',
    subtitle: 'Upload deterministic datasets and run tenant-scoped control-plane tests.'
  },
  {
    path: '/workspace/alert-routing',
    label: 'Alert Routing',
    title: 'Alert Routing',
    subtitle: 'Create, verify, and test alert destinations for the current tenant.'
  },
  {
    path: '/workspace/reconciliation',
    label: 'Reconciliation',
    title: 'Reconciliation',
    subtitle: 'Inspect tenant delivery totals and export reconciliation records.'
  }
];

export const TENANT_HOME_PATH = TENANT_PAGE_META[0].path;

export function getTenantPageMeta(pathname: string): TenantPageMeta {
  const match = TENANT_PAGE_META.find((item) => pathname.startsWith(item.path));
  return match ?? TENANT_PAGE_META[0];
}
