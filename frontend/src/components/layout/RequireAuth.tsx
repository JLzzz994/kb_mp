import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

/** 路由守卫：未登录跳登录页并记录回跳地址 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const location = useLocation();
  const token = localStorage.getItem("kb_access_token");
  if (!token) {
    return <Navigate to={`/login?redirect=${encodeURIComponent(location.pathname)}`} replace />;
  }
  return <>{children}</>;
}
