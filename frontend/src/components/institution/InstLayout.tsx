import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  ArrowLeftRight,
  BadgeCheck,
  FileSearch,
  Info,
  LayoutDashboard,
  Lightbulb,
  LogOut,
  Menu,
  MessagesSquare,
  PieChart,
  X,
  type LucideIcon,
} from "lucide-react";
import { clearInstSession, fetchInstMe, getInstToken, type InstSession } from "@/lib/instAuth";
import { accessBadge, visibleWorkspaces, workspaceForPath } from "@/data/instNav";
import { InstSessionContext } from "./instSessionContext";

const ICONS: Record<string, LucideIcon> = {
  overview: LayoutDashboard,
  ideas: Lightbulb,
  research: FileSearch,
  debate: MessagesSquare,
  portfolio: PieChart,
  approvals: BadgeCheck,
  execution: ArrowLeftRight,
  monitor: Activity,
  about: Info,
};

function loginUrl(next: string) {
  return `/login?mode=inst&next=${encodeURIComponent(next)}`;
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`flex items-center gap-3 ${compact ? "px-4 py-4" : "px-5 py-5"}`}>
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[#c9a15e]/60 bg-[#1b2436] font-display text-lg text-[#e8c98a]">
        旸
      </span>
      <div className="min-w-0">
        <p className="truncate font-display text-base font-semibold tracking-wide text-slate-100">
          旸谷资本
        </p>
        <p className="truncate text-[11px] tracking-wide text-slate-500">
          SVQuant 机构端 · 主观价值投资
        </p>
      </div>
    </div>
  );
}

function SidebarNav({ session, onNavigate }: { session: InstSession; onNavigate?: () => void }) {
  const items = useMemo(() => visibleWorkspaces(session.workspaces), [session.workspaces]);
  return (
    <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-2">
      {items.map((item) => {
        const Icon = ICONS[item.key] || LayoutDashboard;
        const badge = accessBadge(item.access);
        return (
          <NavLink
            key={item.key}
            to={item.path}
            onClick={onNavigate}
            className={({ isActive }) =>
              `group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${
                isActive
                  ? "bg-[#1b2436] text-[#e8c98a]"
                  : "text-slate-400 hover:bg-[#141d2d] hover:text-slate-200"
              }`
            }
          >
            <Icon className="h-4 w-4 shrink-0" aria-hidden />
            <span className="flex-1 truncate">{item.label_cn}</span>
            {badge ? (
              <span className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-500">
                {badge}
              </span>
            ) : null}
          </NavLink>
        );
      })}
    </nav>
  );
}

function SidebarFooter({ session, onLogout }: { session: InstSession; onLogout: () => void }) {
  return (
    <div className="border-t border-[#1e293b] px-4 py-4 text-[11px] text-slate-500">
      <div className="mb-3 flex items-center gap-2">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-[#c9a15e]" />
        <span>模拟环境 · 无真实交易</span>
      </div>
      <p className="mb-3 leading-relaxed">
        {session.demo ? "演示机构数据，仅用于流程验证。" : "受控试点环境。"}
      </p>
      <div className="flex items-center justify-between">
        <NavLink to="/" className="text-slate-500 transition-colors hover:text-slate-300">
          返回个人版
        </NavLink>
        <button
          type="button"
          onClick={onLogout}
          className="inline-flex items-center gap-1 text-slate-500 transition-colors hover:text-slate-300"
        >
          <LogOut className="h-3.5 w-3.5" aria-hidden />
          退出
        </button>
      </div>
    </div>
  );
}

export function InstLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [session, setSession] = useState<InstSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [redirecting, setRedirecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState(false);

  useEffect(() => {
    let alive = true;
    if (!getInstToken()) {
      setRedirecting(true);
      navigate(loginUrl(location.pathname), { replace: true });
      return () => {
        alive = false;
      };
    }
    fetchInstMe()
      .then((next) => {
        if (!alive) return;
        if (!next) {
          setRedirecting(true);
          navigate(loginUrl(location.pathname), { replace: true });
          return;
        }
        setSession(next);
      })
      .catch((ex: unknown) => {
        if (alive) setError(ex instanceof Error ? ex.message : String(ex));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
    // 只在进入机构壳时校验一次；后续页面切换不重复请求
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const current = useMemo(
    () => workspaceForPath(session?.workspaces, location.pathname),
    [session, location.pathname],
  );

  useEffect(() => {
    const onExpired = () => {
      setSession(null);
      navigate("/login?mode=inst", { replace: true });
    };
    window.addEventListener("svq:inst-auth-expired", onExpired);
    return () => window.removeEventListener("svq:inst-auth-expired", onExpired);
  }, [navigate]);

  const logout = () => {
    clearInstSession();
    setSession(null);
    navigate("/login?mode=inst", { replace: true });
  };

  if (loading || redirecting) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0b1220]">
        <div className="text-center">
          <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-slate-700 border-t-[#c9a15e]" />
          <p className="mt-4 text-sm text-slate-400">正在校验机构会话…</p>
        </div>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f5f4f0] px-4">
        <div className="max-w-md rounded-2xl border border-[#e7e3d8] bg-white p-8 text-center">
          <h1 className="font-display text-xl font-semibold text-slate-900">机构会话不可用</h1>
          <p className="mt-3 text-sm text-slate-600">{error || "请重新登录机构端。"}</p>
          <button
            type="button"
            onClick={() => navigate(loginUrl("/inst/overview"), { replace: true })}
            className="mt-6 w-full rounded-xl bg-[#0b1220] py-2.5 text-sm font-semibold text-white transition hover:bg-[#16233a]"
          >
            重新登录
          </button>
        </div>
      </div>
    );
  }

  const denied = current?.access === "none";

  return (
    <InstSessionContext.Provider value={session}>
      <div className="flex min-h-screen bg-[#f5f4f0]">
        <aside className="hidden w-64 shrink-0 flex-col border-r border-[#1e293b] bg-[#0b1220] lg:flex">
          <Brand />
          <div className="mx-5 mb-2 border-t border-[#1e293b]" />
          <SidebarNav session={session} />
          <SidebarFooter session={session} onLogout={logout} />
        </aside>

        {drawer ? (
          <div className="fixed inset-0 z-50 flex lg:hidden">
            <div className="flex w-72 max-w-[85vw] flex-col bg-[#0b1220]">
              <div className="flex items-center justify-between">
                <Brand compact />
                <button
                  type="button"
                  onClick={() => setDrawer(false)}
                  className="mr-3 rounded-lg p-2 text-slate-400 hover:bg-[#141d2d]"
                  aria-label="关闭菜单"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <SidebarNav session={session} onNavigate={() => setDrawer(false)} />
              <SidebarFooter session={session} onLogout={logout} />
            </div>
            <button
              type="button"
              className="flex-1 bg-slate-900/50"
              onClick={() => setDrawer(false)}
              aria-label="关闭菜单遮罩"
            />
          </div>
        ) : null}

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-14 shrink-0 items-center justify-between border-b border-[#e7e3d8] bg-white/80 px-4 backdrop-blur sm:px-6">
            <div className="flex min-w-0 items-center gap-3">
              <button
                type="button"
                onClick={() => setDrawer(true)}
                className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 lg:hidden"
                aria-label="打开菜单"
              >
                <Menu className="h-4 w-4" />
              </button>
              <span className="hidden text-xs text-slate-400 sm:inline">机构端</span>
              <span className="hidden text-xs text-slate-300 sm:inline">/</span>
              <span className="truncate text-sm font-medium text-slate-800">
                {current?.label_cn || "投资驾驶舱"}
              </span>
              {current && accessBadge(current.access) ? (
                <span className="rounded border border-slate-200 px-1.5 py-0.5 text-[10px] text-slate-500">
                  {accessBadge(current.access)}
                </span>
              ) : null}
            </div>
            <div className="flex shrink-0 items-center gap-3">
              <span className="hidden rounded-full border border-[#c9a15e]/40 bg-[#fbf6ea] px-2.5 py-1 text-[11px] text-[#8a6a2f] sm:inline">
                模拟环境 · 无真实交易
              </span>
              <div className="text-right">
                <p className="text-xs font-medium text-slate-800">
                  {session.user.display_name || session.user.username}
                </p>
                <p className="text-[11px] text-slate-500">
                  {session.role_label_cn} · {session.org.name_cn}
                </p>
              </div>
              <button
                type="button"
                onClick={logout}
                className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
              >
                退出
              </button>
            </div>
          </header>

          <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">
            {denied ? (
              <div className="mx-auto max-w-lg rounded-2xl border border-[#e7e3d8] bg-white p-8 text-center">
                <h2 className="font-display text-lg font-semibold text-slate-900">无此工作区权限</h2>
                <p className="mt-2 text-sm text-slate-600">
                  当前角色「{session.role_label_cn}」的权限矩阵不包含该工作区。
                </p>
                <NavLink
                  to="/inst/overview"
                  className="mt-5 inline-block rounded-lg bg-[#0b1220] px-4 py-2 text-sm font-medium text-white"
                >
                  返回投资驾驶舱
                </NavLink>
              </div>
            ) : (
              <Outlet />
            )}
          </main>
        </div>
      </div>
    </InstSessionContext.Provider>
  );
}
