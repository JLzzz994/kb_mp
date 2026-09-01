import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Users,
  ShieldCheck,
  Building2,
  FileUp,
  BookOpen,
  MessagesSquare,
  CircleHelp,
  Target,
  LogOut,
  Menu,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/auth/AuthContext";

/** 导航项 → 所需权限码（17 权限码驱动菜单可见性） */
const NAV_ITEMS = [
  { to: "/", label: "知识运营看板", icon: LayoutDashboard, permission: "dashboard:read", end: true },
  { to: "/users", label: "用户管理", icon: Users, permission: "user:read" },
  { to: "/roles", label: "角色与权限", icon: ShieldCheck, permission: "role:read" },
  { to: "/departments", label: "业务团队", icon: Building2, permission: "dept:read" },
  { to: "/knowledge/import", label: "产品文档导入", icon: FileUp, permission: "knowledge:write" },
  { to: "/knowledge/units", label: "知识资产", icon: BookOpen, permission: "knowledge:read" },
  { to: "/chat", label: "ERP/WMS 智能问答", icon: MessagesSquare, permission: "ai:chat" },
  { to: "/faqs", label: "FAQ 审核", icon: CircleHelp, permission: "faq:read" },
  { to: "/gaps", label: "知识缺口", icon: Target, permission: "gap:read" },
] as const;

export default function AppLayout() {
  const { user, permissions, clearSession } = useAuth();
  const navigate = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const visibleItems = NAV_ITEMS.filter((item) => permissions.includes(item.permission));

  const handleLogout = () => {
    clearSession();
    navigate("/login", { replace: true });
  };

  const sidebar = (
    <nav aria-label="主导航" className="flex h-full flex-col bg-navy text-white/90">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand font-display text-lg font-extrabold text-navy-deep">
          慧
        </span>
        <div>
          <p className="font-display text-[15px] font-extrabold tracking-tight text-white">
            ERP/WMS 产品知识运营
          </p>
          <p className="text-xs text-white/50">Huice Knowledge Operations</p>
        </div>
      </div>

      <div className="mx-5 h-px bg-white/10" />

      <ul className="thin-scrollbar flex-1 space-y-1 overflow-y-auto px-3 py-4">
        {visibleItems.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={"end" in item ? item.end : false}
              onClick={() => setDrawerOpen(false)}
              className={({ isActive }) =>
                cn(
                  "flex min-h-[44px] items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-white/10 text-white shadow-[inset_2px_0_0_0_#36C2A4]"
                    : "text-white/60 hover:bg-white/5 hover:text-white",
                )
              }
            >
              <item.icon className="h-[18px] w-[18px] shrink-0" aria-hidden />
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>

      <div className="border-t border-white/10 p-4">
        <div className="flex items-center gap-3">
          <span
            aria-hidden
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/10 font-display text-sm font-bold text-brand"
          >
            {user?.display_name?.slice(0, 1) ?? "?"}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-white">{user?.display_name ?? "未知用户"}</p>
            <p className="code-text truncate text-white/45">
              {user?.role_codes?.join(" · ") || user?.username}
            </p>
          </div>
          <button
            onClick={handleLogout}
            title="退出登录"
            aria-label="退出登录"
            className="flex h-11 w-11 items-center justify-center rounded-md text-white/60 transition hover:bg-white/10 hover:text-white"
          >
            <LogOut className="h-[18px] w-[18px]" aria-hidden />
          </button>
        </div>
      </div>
    </nav>
  );

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 lg:block">{sidebar}</aside>

      {drawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true">
          <button
            aria-label="关闭导航"
            className="absolute inset-0 bg-navy-deep/60"
            onClick={() => setDrawerOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 w-64 animate-fade-up shadow-2xl">
            <button
              aria-label="关闭导航"
              onClick={() => setDrawerOpen(false)}
              className="absolute right-3 top-4 z-10 flex h-11 w-11 items-center justify-center rounded-md text-white/70 hover:bg-white/10"
            >
              <X className="h-5 w-5" aria-hidden />
            </button>
            {sidebar}
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="sticky top-0 z-40 flex items-center gap-3 border-b border-boundary bg-mist/90 px-4 py-3 backdrop-blur lg:hidden">
          <button
            aria-label="打开导航"
            onClick={() => setDrawerOpen(true)}
            className="flex h-11 w-11 items-center justify-center rounded-md text-ink hover:bg-boundary/50"
          >
            <Menu className="h-5 w-5" aria-hidden />
          </button>
          <span className="font-display font-extrabold text-ink">ERP/WMS 产品知识运营平台</span>
        </div>

        <main className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
