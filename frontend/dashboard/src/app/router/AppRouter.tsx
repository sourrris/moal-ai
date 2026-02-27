import { Navigate, Route, Routes } from 'react-router-dom';

import { AlertsPage } from '../../features/alerts/AlertsPage';
import { EventsPage } from '../../features/events/EventsPage';
import { LoginPage } from '../../features/auth/LoginPage';
import { ModelsPage } from '../../features/models/ModelsPage';
import { OverviewPage } from '../../features/overview/OverviewPage';
import { SettingsPage } from '../../features/settings/SettingsPage';
import { AppShell } from '../../widgets/layout/AppShell';
import { ProtectedRoute } from './ProtectedRoute';

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

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
