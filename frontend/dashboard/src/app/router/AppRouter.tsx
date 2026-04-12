import { Navigate, Route, Routes } from 'react-router-dom';

import { LoginPage } from '../../features/access-auth.content/LoginPage';
import { RegisterPage } from '../../features/access-auth.content/RegisterPage';
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
          <Route path="/" element={<OverviewPage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}