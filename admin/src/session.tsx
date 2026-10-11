import { useSyncExternalStore } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { getLog, getSession, subscribeLog, subscribeSession } from "./api";

export function useSession() {
  return useSyncExternalStore(subscribeSession, getSession, getSession);
}

export function useLog() {
  return useSyncExternalStore(subscribeLog, getLog, getLog);
}

export function RequireAuth() {
  const session = useSession();
  if (!session) return <Navigate to="/login" replace />;
  return <Outlet />;
}
