export type OpsPageMeta = {
  path: string;
  label: string;
  title: string;
  subtitle: string;
};

export const OPS_PAGE_META: OpsPageMeta[] = [
  {
    path: '/ops/tenants',
    label: 'Tenants',
    title: 'Tenant Operations',
    subtitle: 'Create, suspend, and delegate tenant access without leaving the control plane.'
  },
  {
    path: '/ops/connectors',
    label: 'Connectors',
    title: 'Connector Operations',
    subtitle: 'Run, enable, and disable global intelligence feeds from one shared operating surface.'
  },
  {
    path: '/ops/delivery',
    label: 'Delivery',
    title: 'Delivery Logs',
    subtitle: 'Inspect cross-tenant routing outcomes and recent alert delivery attempts.'
  },
  {
    path: '/ops/audit',
    label: 'Audit',
    title: 'Configuration Audit Trail',
    subtitle: 'Review the latest tenant and configuration changes across the control plane.'
  }
];

export const OPS_HOME_PATH = OPS_PAGE_META[0].path;

export function getOpsPageMeta(pathname: string): OpsPageMeta {
  const match = OPS_PAGE_META.find((item) => pathname.startsWith(item.path));
  return match ?? OPS_PAGE_META[0];
}
