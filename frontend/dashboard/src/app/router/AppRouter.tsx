import { Navigate, Route, Routes } from 'react-router-dom';

import { AlertsPage } from '../../features/alert-monitor.content/AlertsPage';
import { EventsPage } from '../../features/event-stream.content/EventsPage';
import { LoginPage } from '../../features/access-auth.content/LoginPage';
import { RegisterPage } from '../../features/access-auth.content/RegisterPage';
import { ModelsPage } from '../../features/model-management.content/ModelsPage';
import { OverviewPage } from '../../features/risk-dashboard.content/OverviewPage';
import { AppShell } from '../../widgets/layout/AppShell';
import { ProtectedRoute } from './ProtectedRoute';

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route path="/overview" element={<OverviewPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/events" element={<EventsPage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/" element={<Navigate to="/overview" replace />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/overview" replace />} />
    </Routes>
  );
}
