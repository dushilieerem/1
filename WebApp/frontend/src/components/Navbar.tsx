import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { Bell, ChevronDown, LogOut, Search, Sparkles } from "lucide-react";
import { FACTOR_NAV_ITEMS, DATA_NAV_ITEMS, NAV_ITEMS, STRATEGY_NAV_ITEMS } from "@/data/nav";
import {
  type AuthUser,
  fetchMe,
  getStoredUser,
  logout,
  subscribeAuth,
} from "@/lib/auth";
import { unreadNotificationCount, UNREAD_CHANGED_EVENT } from "@/lib/communityApi";

function isFactorRoute(pathname: string) {
  return pathname === "/factor" || pathname.startsWith("/factor/");
}

function isStrategyRoute(pathname: string) {
  return pathname === "/strategy" || pathname.startsWith("/strategy/");
}

function isDataRoute(pathname: string) {
  return pathname === "/data" || pathname.startsWith("/data/");
}

function NavDropdown({
  label,
  active,
  items,
}: {
  label: string;
  active: boolean;
  items: readonly { to: string; label: string }[];
}) {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`inline-flex items-center gap-1 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
          active || open
            ? "bg-red-50 text-red-600"
            : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
        }`}
      >
        {label}
        <ChevronDown className={`h-3.5 w-3.5 text-slate-400 transition ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <>
          <button
            type="button"
            aria-label="关闭菜单"
            className="fixed inset-0 z-40 cursor-default"
            onClick={() => setOpen(false)}
          />
          <div className="absolute left-0 top-full z-50 min-w-[11rem] pt-1">
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-lg">
              {items.map(({ to, label: itemLabel }) => (
                <NavLink
                  key={to}
                  to={to}
                  onClick={() => setOpen(false)}
                  className={({ isActive }) =>
                    `block px-4 py-2.5 text-sm transition ${
                      isActive
                        ? "bg-red-50 font-medium text-red-600"
                        : "text-slate-700 hover:bg-slate-50 hover:text-red-600"
                    }`
                  }
                >
                  {itemLabel}
                </NavLink>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function UserMenu({ user }: { user: AuthUser }) {
  const [open, setOpen] = useState(false);
  const initial = (user.display_name || user.username || "?").slice(0, 1).toUpperCase();
  const avatar = (user.avatar_url || "").trim();

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
      >
        {avatar ? (
          <img
            src={avatar}
            alt=""
            className="h-7 w-7 rounded-full object-cover ring-1 ring-slate-200"
          />
        ) : (
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-red-500 to-rose-600 text-xs font-bold text-white">
            {initial}
          </span>
        )}
        <span className="hidden max-w-[7rem] truncate sm:inline">{user.display_name || user.username}</span>
        <ChevronDown className="h-4 w-4 text-slate-400" />
      </button>
      {open && (
        <>
          <button
            type="button"
            aria-label="关闭用户菜单"
            className="fixed inset-0 z-40 cursor-default"
            onClick={() => setOpen(false)}
          />
          <div className="absolute right-0 top-full z-50 min-w-[10rem] pt-1">
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-lg">
              <Link
                to="/community/me"
                onClick={() => setOpen(false)}
                className="block px-4 py-2.5 text-sm text-slate-700 hover:bg-slate-50"
              >
                个人中心
              </Link>
              <Link
                to={`/u/${encodeURIComponent(user.username)}`}
                onClick={() => setOpen(false)}
                className="block px-4 py-2.5 text-sm text-slate-700 hover:bg-slate-50"
              >
                公开主页
              </Link>
              <div className="my-1 border-t border-slate-100" />
              <button
                type="button"
                className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-50"
                onClick={() => {
                  setOpen(false);
                  logout();
                  window.location.assign("/");
                }}
              >
                <LogOut className="h-4 w-4" />
                退出登录
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export function Navbar() {
  const { pathname } = useLocation();
  const factorActive = isFactorRoute(pathname);
  const strategyActive = isStrategyRoute(pathname);
  const dataActive = isDataRoute(pathname);
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser());
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    const unsub = subscribeAuth(() => setUser(getStoredUser()));
    void fetchMe().then((u) => setUser(u));
    const onFocus = () => {
      setUser(getStoredUser());
      void fetchMe().then((u) => setUser(u));
    };
    window.addEventListener("focus", onFocus);
    return () => {
      unsub();
      window.removeEventListener("focus", onFocus);
    };
  }, []);

  useEffect(() => {
    if (!user) {
      setUnread(0);
      return;
    }
    let cancelled = false;
    const pull = () => {
      void unreadNotificationCount()
        .then((d) => {
          if (!cancelled) setUnread(d.total || 0);
        })
        .catch(() => {
          if (!cancelled) setUnread(0);
        });
    };
    pull();
    const t = window.setInterval(pull, 60_000);
    const onFocus = () => pull();
    const onUnreadChanged = (ev: Event) => {
      const detail = (ev as CustomEvent<{ total?: number }>).detail;
      if (typeof detail?.total === "number") {
        setUnread(detail.total);
      } else {
        pull();
      }
    };
    window.addEventListener("focus", onFocus);
    window.addEventListener(UNREAD_CHANGED_EVENT, onUnreadChanged);
    return () => {
      cancelled = true;
      window.clearInterval(t);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener(UNREAD_CHANGED_EVENT, onUnreadChanged);
    };
  }, [user, pathname]);

  return (
    <header className="sticky top-0 z-50 border-b border-slate-200/80 bg-white/90 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-[1440px] items-center gap-8 px-6">
        <NavLink to="/" className="flex shrink-0 items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 text-sm font-extrabold text-white shadow-sm">
            SV
          </div>
          <span className="text-lg font-bold tracking-tight text-slate-900">SVQuant</span>
        </NavLink>

        <nav className="hidden items-center gap-1 md:flex">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              `rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-red-50 text-red-600"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            首页
          </NavLink>
          <NavLink
            to="/community"
            className={({ isActive }) =>
              `rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-red-50 text-red-600"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            社区
          </NavLink>
          <NavLink
            to="/news"
            className={({ isActive }) =>
              `rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                isActive || pathname.startsWith("/news/")
                  ? "bg-red-50 text-red-600"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            资讯
          </NavLink>
          {user ? (
            <>
              {NAV_ITEMS.filter(
                (x) => x.to !== "/" && x.to !== "/community" && x.to !== "/news",
              ).map(({ to, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    `rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-red-50 text-red-600"
                        : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                    }`
                  }
                >
                  {label}
                </NavLink>
              ))}
              <NavDropdown label="数据" active={dataActive} items={DATA_NAV_ITEMS} />
              <NavDropdown label="策略" active={strategyActive} items={STRATEGY_NAV_ITEMS} />
              <NavDropdown label="因子" active={factorActive} items={FACTOR_NAV_ITEMS} />
            </>
          ) : null}
        </nav>

        <div className="ml-auto flex items-center gap-3">
          <div className="hidden items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2 lg:flex lg:w-72">
            <Search className="h-4 w-4 shrink-0 text-slate-400" />
            <input
              type="search"
              placeholder="搜索数据表、因子、策略…"
              className="w-full bg-transparent text-sm text-slate-700 outline-none placeholder:text-slate-400"
            />
            <button
              type="button"
              className="flex shrink-0 items-center gap-1 rounded-md bg-slate-900 px-2 py-0.5 text-[10px] font-semibold text-white"
            >
              <Sparkles className="h-3 w-3" />
              AI
            </button>
          </div>

          {user ? (
            <Link
              to="/community/me?tab=messages"
              className="relative rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-700"
              aria-label="消息"
            >
              <Bell className="h-5 w-5" />
              {unread > 0 && (
                <span className="absolute -right-0.5 -top-0.5 inline-flex min-w-[1.05rem] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold leading-4 text-white ring-2 ring-white">
                  {unread > 99 ? "99+" : unread}
                </span>
              )}
            </Link>
          ) : null}

          {user ? (
            <UserMenu user={user} />
          ) : (
            <Link
              to={
                pathname.startsWith("/community")
                  ? `/login?next=${encodeURIComponent(pathname)}`
                  : "/login"
              }
              className="rounded-xl border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              登录
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
