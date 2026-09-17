import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Database, FileText, Home, MessageSquare } from "lucide-react";
import { clearSession, getStoredUser } from "@/lib/auth";

const NAV = [
  { to: "/datasets", label: "知识库", icon: Database },
  { to: "/chats", label: "聊天", icon: MessageSquare },
  { to: "/files", label: "文件管理", icon: FileText },
] as const;

export function AppShell() {
  const user = getStoredUser();
  const navigate = useNavigate();
  const location = useLocation();
  const initial = (user?.display_name || user?.username || "A").slice(0, 1).toUpperCase();
  const isChatRoom = /^\/chats\/[^/]+$/.test(location.pathname);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 shrink-0 border-b border-[var(--kh-line)] bg-white/75 backdrop-blur-xl">
        <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-6 px-4">
          <NavLink to="/" className="flex shrink-0 items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--kh-cyan)] to-[var(--kh-teal-deep)] text-xs font-bold text-white shadow-md shadow-teal-700/25">
              KH
            </div>
            <span className="kh-display hidden text-sm font-semibold text-[var(--kh-ink)] sm:inline">
              知识库平台
            </span>
          </NavLink>

          <nav className="mx-auto flex items-center rounded-full border border-[var(--kh-line)] bg-white/70 p-1 shadow-sm">
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                `rounded-full p-2 transition ${
                  isActive
                    ? "bg-[var(--kh-ink)] text-white"
                    : "text-slate-600 hover:bg-[var(--kh-mist)]"
                }`
              }
              title="首页"
            >
              <Home className="h-4 w-4" />
            </NavLink>
            {NAV.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm transition ${
                    isActive
                      ? "bg-[var(--kh-ink)] font-medium text-white"
                      : "text-slate-600 hover:bg-[var(--kh-mist)]"
                  }`
                }
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
              </NavLink>
            ))}
          </nav>

          <button
            type="button"
            onClick={() => navigate("/settings/models")}
            className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-[var(--kh-amber)] to-[#c47b0a] text-sm font-semibold text-white shadow-md shadow-amber-700/20"
            title="个人中心"
          >
            {initial}
          </button>
        </div>
      </header>

      <main
        className={
          isChatRoom
            ? "flex min-h-0 flex-1 flex-col"
            : "mx-auto w-full max-w-[1600px] flex-1 px-4 py-6"
        }
      >
        <Outlet />
      </main>

      {!isChatRoom ? (
        <div className="fixed bottom-3 right-3 hidden text-[10px] text-slate-400 md:block">
          <button
            type="button"
            className="hover:underline"
            onClick={() => {
              clearSession();
              navigate("/login");
            }}
          >
            退出
          </button>
        </div>
      ) : null}
    </div>
  );
}
