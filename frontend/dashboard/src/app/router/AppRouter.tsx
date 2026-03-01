import { Navigate, Route, Routes } from 'react-router-dom';

import { AlertsPage } from '../../features/alert-monitor.content/AlertsPage';
import { EventsPage } from '../../features/event-stream.content/EventsPage';
import { AuthCallbackPage } from '../../features/access-auth.content/AuthCallbackPage';
import { LoginPage } from '../../features/access-auth.content/LoginPage';
import { ModelsPage } from '../../features/model-management.content/ModelsPage';
import { OverviewPage } from '../../features/risk-dashboard.content/OverviewPage';
import { SettingsPage } from '../../features/platform-settings.content/SettingsPage';
import { AppShell } from '../../widgets/layout/AppShell';
import { ProtectedRoute } from './ProtectedRoute';

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/auth/callback" element={<AuthCallbackPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route path="/overview" element={<OverviewPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/events" element={<EventsPage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/" element={<Navigate to="/overview" replace />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/overview" replace />} />
    </Routes>
  );
}
