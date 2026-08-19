/**
 * 认证上下文：持有 CurrentUserInfo + 17 权限码子集，
 * 驱动菜单可见性与按钮级权限（PermissionGate）。
 */
import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { TOKEN_KEY, USER_KEY, PERMS_KEY } from "@/api/client";
import type { CurrentUserInfo } from "@/api/auth";

interface AuthState {
  user: CurrentUserInfo | null;
  permissions: string[];
  isAuthed: boolean;
  setSession: (user: CurrentUserInfo, permissions: string[]) => void;
  clearSession: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

function readStored(): { user: CurrentUserInfo | null; permissions: string[] } {
  try {
    const token = localStorage.getItem(TOKEN_KEY);
    const user = localStorage.getItem(USER_KEY);
    const perms = localStorage.getItem(PERMS_KEY);
    if (!token) return { user: null, permissions: [] };
    return {
      user: user ? (JSON.parse(user) as CurrentUserInfo) : null,
      permissions: perms ? (JSON.parse(perms) as string[]) : [],
    };
  } catch {
    return { user: null, permissions: [] };
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [stored] = useState(readStored);
  const [user, setUser] = useState<CurrentUserInfo | null>(stored.user);
  const [permissions, setPermissions] = useState<string[]>(stored.permissions);

  const setSession = useCallback((u: CurrentUserInfo, perms: string[]) => {
    setUser(u);
    setPermissions(perms);
  }, []);

  const clearSession = useCallback(() => {
    setUser(null);
    setPermissions([]);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(PERMS_KEY);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      permissions,
      isAuthed: Boolean(localStorage.getItem(TOKEN_KEY)),
      setSession,
      clearSession,
    }),
    [user, permissions, setSession, clearSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth 必须在 AuthProvider 内使用");
  return ctx;
}

/** 是否拥有某个权限码（如 "knowledge:write"） */
export function usePermission(): (code: string) => boolean {
  const { permissions } = useAuth();
  return useCallback((code: string) => permissions.includes(code), [permissions]);
}

/** 按钮级权限门控：无权限时默认不渲染（hide），也可 fallback 展示提示 */
export function PermissionGate({
  code,
  children,
  fallback = null,
}: {
  code: string;
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const can = usePermission();
  if (!can(code)) return <>{fallback}</>;
  return <>{children}</>;
}
