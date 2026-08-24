import { NavLink, Outlet } from "react-router-dom";
import { clearSession, getStoredUser } from "@/lib/auth";
import { BookOpen, CircleHelp, KeyRound, UserRound } from "lucide-react";

const SIDE = [
  { to: "/settings/guide", label: "使用说明", icon: CircleHelp },
  { to: "/settings/models", label: "模型供应商", icon: KeyRound },
  { to: "/settings/api", label: "API", icon: BookOpen },
  { to: "/settings/account", label: "账号", icon: UserRound },
] as const;

export function SettingsLayout() {
  const user = getStoredUser();
  return (
    <div className="-mx-4 -mt-6 flex min-h-[calc(100vh-3.5rem)]">
      <aside className="flex w-56 shrink-0 flex-col border-r border-slate-200 bg-white px-3 py-4">
        <div className="mb-4 px-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-violet-500 text-sm font-bold text-white">
            {(user?.display_name || user?.username || "A").slice(0, 1).toUpperCase()}
          </div>
          <p className="mt-2 truncate text-sm font-medium">{user?.display_name || user?.username}</p>
          <p className="text-xs text-slate-400">管理员</p>
        </div>
        <nav className="space-y-0.5">
          {SIDE.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
                  isActive ? "bg-slate-100 font-medium text-slate-900" : "text-slate-600 hover:bg-slate-50"
                }`
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <button
          type="button"
          className="mt-auto rounded-lg px-3 py-2 text-left text-sm text-slate-500 hover:bg-slate-50"
          onClick={() => {
            clearSession();
            window.location.href = "/login";
          }}
        >
          登出
        </button>
      </aside>
      <div className="min-w-0 flex-1 bg-[#fafafa] p-6">
        <Outlet />
      </div>
    </div>
  );
}
