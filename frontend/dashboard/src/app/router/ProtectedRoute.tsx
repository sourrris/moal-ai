import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../state/auth-context";

export function ProtectedRoute() {
  const { token } = useAuth();
  const location = useLocation();

  if (!token) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <Outlet />;
}
