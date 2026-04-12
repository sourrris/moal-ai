import { Navigate, Route, Routes } from "react-router-dom";

import { LoginPage } from "../../features/access-auth.content/LoginPage";
import { RegisterPage } from "../../features/access-auth.content/RegisterPage";
import { AlertsPage } from "../../features/alerts.content/AlertsPage";
import { ModelsPage } from "../../features/models.content/ModelsPage";
import { OverviewPage } from "../../features/risk-dashboard.content/OverviewPage";
import { UserProfilePage } from "../../features/user-profile.content/UserProfilePage";
import { AppShell } from "../../widgets/layout/AppShell";
import { ProtectedRoute } from "./ProtectedRoute";

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/users/:identifier" element={<UserProfilePage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
