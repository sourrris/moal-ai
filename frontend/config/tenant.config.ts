export type TenantFeatureToggles = {
  nav: {
    overview: boolean;
    alerts: boolean;
    events: boolean;
    models: boolean;
    settings: boolean;
  };
  widgets: {
    trend: boolean;
    severity: boolean;
    sourceStatus: boolean;
    connectorRuns: boolean;
    criticalAlerts: boolean;
  };
};

export type TenantBranding = {
  appName: string;
  badgeText: string;
};

export type TenantDashboardConfig = {
  tenantId: string;
  branding: TenantBranding;
  features: TenantFeatureToggles;
};

export const TENANT_CONFIGS: Record<string, TenantDashboardConfig> = {
  default: {
    tenantId: "default",
    branding: {
      appName: "Aegis Risk",
      badgeText: "AR",
    },
    features: {
      nav: {
        overview: true,
        alerts: true,
        events: true,
        models: true,
        settings: true,
      },
      widgets: {
        trend: true,
        severity: true,
        sourceStatus: true,
        connectorRuns: true,
        criticalAlerts: true,
      },
    },
  },
  "tenant-alpha": {
    tenantId: "tenant-alpha",
    branding: {
      appName: "Aegis Risk Alpha",
      badgeText: "AA",
    },
    features: {
      nav: {
        overview: true,
        alerts: true,
        events: true,
        models: true,
        settings: true,
      },
      widgets: {
        trend: true,
        severity: true,
        sourceStatus: true,
        connectorRuns: true,
        criticalAlerts: true,
      },
    },
  },
  "tenant-beta": {
    tenantId: "tenant-beta",
    branding: {
      appName: "Aegis Risk Beta",
      badgeText: "AB",
    },
    features: {
      nav: {
        overview: true,
        alerts: true,
        events: true,
        models: false,
        settings: true,
      },
      widgets: {
        trend: true,
        severity: true,
        sourceStatus: true,
        connectorRuns: true,
        criticalAlerts: false,
      },
    },
  },
};

export function resolveTenantConfig(tenantId: string): TenantDashboardConfig {
  if (!tenantId || tenantId === "all") {
    return TENANT_CONFIGS.default;
  }
  return TENANT_CONFIGS[tenantId] ?? TENANT_CONFIGS.default;
}
