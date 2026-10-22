import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { Bell, ChevronDown, LogOut, Menu, Search, Sparkles, X } from "lucide-react";
import {
  FACTOR_NAV_ITEMS,
  DATA_NAV_ITEMS,
  HELP_NAV,
  PAPER_NAV,
  STRATEGY_NAV_ITEMS,
} from "@/data/nav";
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

function isHelpRoute(pathname: string) {
  return (
    pathname === "/help" ||
    pathname.startsWith("/help/") ||
    pathname === "/data/api-docs"
  );
}

function navLinkClass(isActive: boolean) {
  return `rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
    isActive
      ? "bg-red-50 text-red-600"
      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
  }`;
}

function drawerLinkClass(isActive: boolean) {
  return `block rounded-lg px-3 py-2.5 text-sm transition ${
    isActive
      ? "bg-red-50 font-medium text-red-600"
      : "text-slate-700 hover:bg-slate-50 hover:text-red-600"
  }`;
}

function loginWithNext(path: string) {
  return `/login?next=${encodeURIComponent(path)}`;
}

function NavDropdown({
  label,
  active,
  items,
  /** 未登录：展开后点任一项 → 登录（带 next） */
  gateAuth = false,
}: {
  label: string;
  active: boolean;
  items: readonly { to: string; label: string }[];
  gateAuth?: boolean;
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
                  to={gateAuth ? loginWithNext(to) : to}
                  onClick={() => setOpen(false)}
                  className={({ isActive }) =>
                    `block px-4 py-2.5 text-sm transition ${
                      !gateAuth && isActive
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
        className="flex shrink-0 items-center gap-1.5 rounded-xl border border-slate-200 p-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 sm:gap-2 sm:px-3 sm:py-1.5"
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
        <span className="hidden max-w-[5.5rem] truncate sm:inline sm:max-w-[7rem]">
          {user.display_name || user.username}
        </span>
        <ChevronDown className="hidden h-4 w-4 text-slate-400 sm:block" />
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

function DrawerSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mt-4 first:mt-0">
      <p className="mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        {title}
      </p>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

export function Navbar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const factorActive = isFactorRoute(pathname);
  const strategyActive = isStrategyRoute(pathname);
  const dataActive = isDataRoute(pathname);
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser());
  const [unread, setUnread] = useState(0);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [navQ, setNavQ] = useState("");

  const submitNavSearch = (e: FormEvent) => {
    e.preventDefault();
    const q = navQ.trim();
    if (!q) {
      navigate("/search");
      return;
    }
    navigate(`/search?q=${encodeURIComponent(q)}`);
  };

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

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!mobileOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [mobileOpen]);

  const closeMobile = () => setMobileOpen(false);

  const primaryLinks = (
    <>
      <NavLink to="/" end className={({ isActive }) => navLinkClass(isActive)}>
        首页
      </NavLink>
      <NavLink to="/community" className={({ isActive }) => navLinkClass(isActive)}>
        社区
      </NavLink>
      <NavLink
        to="/news"
        className={({ isActive }) =>
          navLinkClass(isActive || pathname.startsWith("/news/"))
        }
      >
        资讯
      </NavLink>
      <NavLink
        to={user ? PAPER_NAV.to : loginWithNext(PAPER_NAV.to)}
        className={({ isActive }) =>
          navLinkClass(Boolean(user) && (isActive || pathname.startsWith("/paper")))
        }
      >
        {PAPER_NAV.label}
      </NavLink>
      {/* 未登录也展示数据/策略/因子菜单；点子项再跳登录 */}
      <NavDropdown
        label="数据"
        active={dataActive}
        items={DATA_NAV_ITEMS}
        gateAuth={!user}
      />
      <NavDropdown
        label="策略"
        active={strategyActive}
        items={STRATEGY_NAV_ITEMS}
        gateAuth={!user}
      />
      <NavDropdown
        label="因子"
        active={factorActive}
        items={FACTOR_NAV_ITEMS}
        gateAuth={!user}
      />
      <NavLink
        to={HELP_NAV.to}
        className={({ isActive }) =>
          navLinkClass(isActive || isHelpRoute(pathname))
        }
      >
        {HELP_NAV.label}
      </NavLink>
    </>
  );

  const loginTo = pathname.startsWith("/community")
    ? `/login?next=${encodeURIComponent(pathname)}`
    : "/login";

  return (
    <>
    <header className="sticky top-0 z-50 border-b border-slate-200/80 bg-white/90 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-[1440px] items-center gap-2 px-3 sm:h-16 sm:gap-8 sm:px-6">
        <NavLink to="/" className="flex min-w-0 shrink-0 items-center gap-2 sm:gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-xs font-extrabold text-white shadow-sm sm:h-9 sm:w-9 sm:text-sm">
            SV
          </div>
          <span className="truncate text-base font-bold tracking-tight text-slate-900 sm:text-lg">
            SVQuant
          </span>
        </NavLink>

        <nav className="hidden items-center gap-1 md:flex">{primaryLinks}</nav>

        <div className="ml-auto flex min-w-0 items-center gap-0.5 sm:gap-2">
          <form
            onSubmit={submitNavSearch}
            className="hidden items-center gap-1.5 rounded-xl border border-slate-200 bg-slate-50/80 py-1.5 pl-3 pr-1.5 lg:flex lg:w-80"
          >
            <Search className="h-4 w-4 shrink-0 text-slate-400" />
            <input
              type="search"
              value={navQ}
              onChange={(e) => setNavQ(e.target.value)}
              placeholder="搜社区帖、资讯…"
              className="min-w-0 flex-1 bg-transparent text-sm text-slate-700 outline-none placeholder:text-slate-400"
              aria-label="全局搜索"
            />
            <button
              type="submit"
              className="shrink-0 rounded-lg bg-slate-900 px-2.5 py-1 text-xs font-semibold text-white hover:bg-slate-800"
            >
              搜索
            </button>
            <Link
              to="/ai"
              className="flex shrink-0 items-center gap-0.5 rounded-lg border border-slate-200 bg-white px-1.5 py-1 text-[10px] font-semibold text-slate-600 hover:border-sky-300 hover:bg-sky-50 hover:text-sky-700"
              title="AI 模块"
              aria-label="AI 模块"
            >
              <Sparkles className="h-3 w-3" />
              AI
            </Link>
          </form>

          <Link
            to="/search"
            className="shrink-0 rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-700 sm:p-2 lg:hidden"
            aria-label="搜索"
          >
            <Search className="h-5 w-5" />
          </Link>
          <Link
            to={user ? "/ai" : loginWithNext("/ai")}
            className="shrink-0 rounded-lg p-1.5 text-sky-600 hover:bg-sky-50 hover:text-sky-700 sm:p-2 lg:hidden"
            aria-label="AI 模块"
            title="AI 模块"
          >
            <Sparkles className="h-5 w-5" />
          </Link>

          {user ? (
            <Link
              to="/community/me?tab=messages"
              className="relative shrink-0 rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-700 sm:p-2"
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
              to={loginTo}
              className="hidden rounded-xl border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 md:inline-flex"
            >
              登录
            </Link>
          )}

          <button
            type="button"
            className="shrink-0 rounded-lg p-1.5 text-slate-600 hover:bg-slate-100 sm:p-2 md:hidden"
            aria-label={mobileOpen ? "关闭菜单" : "打开菜单"}
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen((v) => !v)}
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>
    </header>

      {mobileOpen && typeof document !== "undefined"
        ? createPortal(
            <div className="md:hidden" role="dialog" aria-modal="true" aria-label="导航菜单">
              <button
                type="button"
                className="fixed inset-0 z-[60] bg-slate-900/40"
                aria-label="关闭菜单遮罩"
                onClick={closeMobile}
              />
              <div className="fixed inset-y-0 right-0 z-[70] flex h-[100dvh] w-[min(72vw,15.5rem)] flex-col border-l border-slate-200 bg-white shadow-xl">
                <div className="flex h-14 shrink-0 items-center justify-between border-b border-slate-100 px-4">
                  <span className="text-sm font-semibold text-slate-900">菜单</span>
                  <button
                    type="button"
                    className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"
                    aria-label="关闭"
                    onClick={closeMobile}
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>
                <nav className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 py-3">
                  <DrawerSection title="导航">
                    <NavLink to="/" end onClick={closeMobile} className={({ isActive }) => drawerLinkClass(isActive)}>
                      首页
                    </NavLink>
                    <NavLink to="/community" onClick={closeMobile} className={({ isActive }) => drawerLinkClass(isActive)}>
                      社区
                    </NavLink>
                    <NavLink
                      to="/news"
                      onClick={closeMobile}
                      className={({ isActive }) =>
                        drawerLinkClass(isActive || pathname.startsWith("/news/"))
                      }
                    >
                      资讯
                    </NavLink>
                    <NavLink
                      to={user ? PAPER_NAV.to : loginWithNext(PAPER_NAV.to)}
                      onClick={closeMobile}
                      className={({ isActive }) =>
                        drawerLinkClass(
                          Boolean(user) &&
                            (isActive || pathname.startsWith("/paper")),
                        )
                      }
                    >
                      {PAPER_NAV.label}
                    </NavLink>
                    <NavLink
                      to={user ? "/ai" : loginWithNext("/ai")}
                      onClick={closeMobile}
                      className={({ isActive }) =>
                        drawerLinkClass(
                          Boolean(user) &&
                            (isActive || pathname.startsWith("/ai")),
                        )
                      }
                    >
                      <span className="inline-flex items-center gap-1.5">
                        <Sparkles className="h-3.5 w-3.5" />
                        AI 模块
                      </span>
                    </NavLink>
                    <NavLink
                      to={HELP_NAV.to}
                      onClick={closeMobile}
                      className={({ isActive }) =>
                        drawerLinkClass(isActive || isHelpRoute(pathname))
                      }
                    >
                      {HELP_NAV.label}
                    </NavLink>
                  </DrawerSection>

                  <DrawerSection title="数据">
                    {DATA_NAV_ITEMS.map(({ to, label }) => (
                      <NavLink
                        key={to}
                        to={user ? to : loginWithNext(to)}
                        onClick={closeMobile}
                        className={({ isActive }) =>
                          drawerLinkClass(Boolean(user) && isActive)
                        }
                      >
                        {label}
                      </NavLink>
                    ))}
                  </DrawerSection>
                  <DrawerSection title="策略">
                    {STRATEGY_NAV_ITEMS.map(({ to, label }) => (
                      <NavLink
                        key={to}
                        to={user ? to : loginWithNext(to)}
                        onClick={closeMobile}
                        className={({ isActive }) =>
                          drawerLinkClass(Boolean(user) && isActive)
                        }
                      >
                        {label}
                      </NavLink>
                    ))}
                  </DrawerSection>
                  <DrawerSection title="因子">
                    {FACTOR_NAV_ITEMS.map(({ to, label }) => (
                      <NavLink
                        key={to}
                        to={user ? to : loginWithNext(to)}
                        onClick={closeMobile}
                        className={({ isActive }) =>
                          drawerLinkClass(Boolean(user) && isActive)
                        }
                      >
                        {label}
                      </NavLink>
                    ))}
                  </DrawerSection>

                  {user ? (
                    <DrawerSection title="我的">
                        <NavLink
                          to="/community/me"
                          onClick={closeMobile}
                          className={({ isActive }) => drawerLinkClass(isActive)}
                        >
                          个人中心
                        </NavLink>
                        <NavLink
                          to="/community/me?tab=messages"
                          onClick={closeMobile}
                          className={({ isActive }) => drawerLinkClass(isActive)}
                        >
                          消息{unread > 0 ? ` (${unread > 99 ? "99+" : unread})` : ""}
                        </NavLink>
                        <NavLink
                          to={`/u/${encodeURIComponent(user.username)}`}
                          onClick={closeMobile}
                          className={({ isActive }) => drawerLinkClass(isActive)}
                        >
                          公开主页
                        </NavLink>
                        <button
                          type="button"
                          className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-50"
                          onClick={() => {
                            closeMobile();
                            logout();
                            window.location.assign("/");
                          }}
                        >
                          <LogOut className="h-4 w-4" />
                          退出登录
                        </button>
                      </DrawerSection>
                  ) : (
                    <DrawerSection title="账户">
                      <Link
                        to={loginTo}
                        onClick={closeMobile}
                        className="block rounded-lg bg-red-600 px-3 py-2.5 text-center text-sm font-semibold text-white"
                      >
                        登录
                      </Link>
                      <Link
                        to="/register"
                        onClick={closeMobile}
                        className="mt-1 block rounded-lg px-3 py-2.5 text-center text-sm font-medium text-slate-700 hover:bg-slate-50"
                      >
                        注册
                      </Link>
                    </DrawerSection>
                  )}
                </nav>
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
