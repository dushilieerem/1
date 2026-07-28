import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Activity,
  Bell,
  Bookmark,
  ChevronRight,
  FilePenLine,
  FileText,
  Gauge,
  LayoutDashboard,
  Shield,
  UserRound,
} from "lucide-react";
import { getStoredUser } from "@/lib/auth";
import { getMyAgentUsage, type AgentUsageMe } from "@/lib/agentApi";
import { AuthorAvatar, CommunityPageShell } from "@/components/community/communityUi";
import {
  MeDraftsPanel,
  MeFavoritesPanel,
  MeMessagesPanel,
  MeModPanel,
  MePostsPanel,
  MeUsagePanel,
} from "@/pages/CommunityMePanels";

export type MeTab =
  | "workspace"
  | "usage"
  | "messages"
  | "mine"
  | "drafts"
  | "favorites"
  | "mod";

const TAB_IDS: MeTab[] = [
  "workspace",
  "usage",
  "messages",
  "mine",
  "drafts",
  "favorites",
  "mod",
];

function parseTab(raw: string | null, isAdmin: boolean): MeTab {
  if (raw && TAB_IDS.includes(raw as MeTab)) {
    if (raw === "mod" && !isAdmin) return "workspace";
    return raw as MeTab;
  }
  return "workspace";
}

const SIDE_NAV: {
  id: MeTab;
  label: string;
  icon: typeof Bell;
  adminOnly?: boolean;
}[] = [
  { id: "workspace", label: "工作台", icon: LayoutDashboard },
  { id: "usage", label: "AI 用量", icon: Activity },
  { id: "messages", label: "消息中心", icon: Bell },
  { id: "mine", label: "我的发帖", icon: FileText },
  { id: "drafts", label: "草稿箱", icon: FilePenLine },
  { id: "favorites", label: "我的收藏", icon: Bookmark },
  { id: "mod", label: "管理仓", icon: Shield, adminOnly: true },
];

const QUICK_LINKS: {
  id: MeTab;
  title: string;
  desc: string;
  icon: typeof Bell;
  iconWrap: string;
  card: string;
}[] = [
  {
    id: "messages",
    title: "消息中心",
    desc: "回复 · @ · 赞踩通知",
    icon: Bell,
    iconWrap: "bg-sky-500 text-white shadow-sky-200/80",
    card: "from-sky-50/90 to-white hover:border-sky-200",
  },
  {
    id: "mine",
    title: "我的发帖",
    desc: "已发布内容与管理",
    icon: FileText,
    iconWrap: "bg-violet-500 text-white shadow-violet-200/80",
    card: "from-violet-50/90 to-white hover:border-violet-200",
  },
  {
    id: "drafts",
    title: "草稿箱",
    desc: "未发布草稿继续写",
    icon: FilePenLine,
    iconWrap: "bg-amber-500 text-white shadow-amber-200/80",
    card: "from-amber-50/90 to-white hover:border-amber-200",
  },
  {
    id: "favorites",
    title: "我的收藏",
    desc: "收藏过的帖子",
    icon: Bookmark,
    iconWrap: "bg-emerald-500 text-white shadow-emerald-200/80",
    card: "from-emerald-50/90 to-white hover:border-emerald-200",
  },
];

export function CommunityMePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [user] = useState(() => getStoredUser());
  const isAdmin = user?.role === "admin";
  const tab = parseTab(searchParams.get("tab"), isAdmin);
  const [usage, setUsage] = useState<AgentUsageMe | null>(null);
  const name = user?.display_name || user?.username || "用户";
  const initial = name.slice(0, 1).toUpperCase();
  const roleLabel = isAdmin ? "管理员" : "用户";
  const sideNav = SIDE_NAV.filter((n) => !n.adminOnly || isAdmin);

  const setTab = (id: MeTab) => {
    setSearchParams(id === "workspace" ? {} : { tab: id }, { replace: true });
  };

  useEffect(() => {
    if (!user || tab !== "workspace") return;
    let cancelled = false;
    void getMyAgentUsage(1)
      .then((u) => {
        if (!cancelled) setUsage(u);
      })
      .catch(() => {
        if (!cancelled) setUsage(null);
      });
    return () => {
      cancelled = true;
    };
  }, [user, tab]);

  const usedPct = useMemo(() => {
    if (!usage || !usage.quota_daily) return 0;
    return Math.min(100, Math.round((usage.used_today / usage.quota_daily) * 100));
  }, [usage]);

  return (
    <CommunityPageShell className="!min-h-[calc(100vh-4rem)]">
      <div className="relative flex min-h-[calc(100vh-4rem)] bg-[radial-gradient(ellipse_at_top,_#f8fafc_0%,_#eef1f6_55%,_#e8eef5_100%)]">
        <aside className="flex w-[200px] shrink-0 flex-col border-r border-slate-200/70 bg-white/90 shadow-[2px_0_24px_rgba(15,23,42,0.04)] backdrop-blur-md sm:w-[220px]">
          <div className="relative overflow-hidden border-b border-slate-100 px-4 pb-5 pt-6">
            <div
              className="pointer-events-none absolute -right-6 -top-8 h-28 w-28 rounded-full bg-slate-200/40 blur-2xl"
              aria-hidden
            />
            <div className="relative flex items-center gap-3">
              {user?.username ? (
                <Link
                  to={`/u/${encodeURIComponent(user.username)}`}
                  className="shrink-0"
                  title="我的主页"
                >
                  <AuthorAvatar
                    name={name}
                    src={user.avatar_url}
                    size="lg"
                  />
                </Link>
              ) : (
                <span className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-800 text-base font-bold text-white shadow-md ring-2 ring-white">
                  {initial}
                </span>
              )}
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-slate-900">{name}</p>
                <p className="truncate text-xs text-slate-500">
                  {roleLabel}
                  {user?.username ? ` · ${user.username}` : ""}
                </p>
                {user?.username ? (
                  <Link
                    to={`/u/${encodeURIComponent(user.username)}`}
                    className="mt-1 inline-flex items-center gap-1 text-[11px] font-medium text-red-600 hover:text-red-500"
                  >
                    <UserRound className="h-3 w-3" />
                    我的主页
                  </Link>
                ) : null}
              </div>
            </div>
          </div>

          <nav className="flex-1 space-y-1 p-2.5">
            {sideNav.map((item) => {
              const Icon = item.icon;
              const active = tab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setTab(item.id)}
                  className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-left text-sm transition ${
                    active
                      ? "bg-slate-900 font-semibold text-white shadow-sm"
                      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                  }`}
                >
                  <Icon className={`h-4 w-4 ${active ? "text-white" : "text-slate-400"}`} />
                  {item.label}
                </button>
              );
            })}
          </nav>

          <div className="border-t border-slate-100 p-3">
            <Link
              to="/community"
              className="block rounded-lg px-2 py-2 text-center text-xs font-medium text-slate-500 transition hover:bg-slate-50 hover:text-slate-800"
            >
              浏览社区 Feed
            </Link>
          </div>
        </aside>

        <main className="min-w-0 flex-1 overflow-hidden p-3 sm:p-4 lg:p-5">
          {tab === "workspace" ? (
            <div className="h-full overflow-auto animate-fade-up">
              {/* 欢迎横幅：浅色 */}
              <section className="relative mb-5 overflow-hidden rounded-3xl border border-slate-200/80 bg-gradient-to-br from-white via-sky-50/80 to-amber-50/70 p-6 shadow-sm sm:p-7">
                <div
                  className="pointer-events-none absolute inset-0 opacity-60"
                  style={{
                    backgroundImage:
                      "radial-gradient(circle at 10% 20%, rgba(14,165,233,0.12) 0%, transparent 42%), radial-gradient(circle at 90% 0%, rgba(251,146,60,0.14) 0%, transparent 40%)",
                  }}
                  aria-hidden
                />
                <div className="relative">
                  <p className="text-xs font-medium tracking-wide text-slate-400">
                    SVQUANT · 个人中心
                  </p>
                  <h1 className="mt-1.5 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
                    你好，{name}
                  </h1>
                  <p className="mt-2 max-w-md text-sm text-slate-500">
                    管理发帖、草稿、消息与 AI 用量；公开主页请从右上角菜单进入。
                  </p>
                </div>
              </section>

              <p className="mb-3 text-xs font-semibold tracking-wide text-slate-400">
                AI 用量
              </p>
              <button
                type="button"
                onClick={() => setTab("usage")}
                className="group mb-5 flex w-full items-center gap-4 overflow-hidden rounded-2xl border border-slate-200/90 bg-white px-5 py-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md"
              >
                <span className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-red-500 to-orange-400 text-white shadow-md shadow-orange-200/60">
                  <Gauge className="h-5 w-5" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <p className="text-sm font-semibold text-slate-900">
                      Agent 日配额{" "}
                      <span className="tabular-nums text-slate-700">
                        {usage ? `${usage.used_today} / ${usage.quota_daily}` : "—"}
                      </span>
                    </p>
                    <span className="inline-flex items-center gap-0.5 text-xs font-semibold text-slate-500 group-hover:gap-1 group-hover:text-slate-800">
                      查看明细
                      <ChevronRight className="h-3.5 w-3.5" />
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500">
                    剩余 {usage?.remaining ?? "—"}
                    {usage?.day ? ` · ${usage.day}` : ""}
                  </p>
                  <div className="mt-2.5 h-2 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-red-500 via-rose-500 to-orange-400 transition-all"
                      style={{ width: `${usedPct}%` }}
                    />
                  </div>
                </div>
              </button>

              <p className="mb-3 text-xs font-semibold tracking-wide text-slate-400">
                快捷入口
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                {QUICK_LINKS.map((item) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setTab(item.id)}
                      className={`group flex items-start gap-3.5 rounded-2xl border border-slate-200/70 bg-gradient-to-br p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md ${item.card}`}
                    >
                      <span
                        className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl shadow-md ${item.iconWrap}`}
                      >
                        <Icon className="h-5 w-5" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-sm font-semibold text-slate-900">{item.title}</p>
                          <ChevronRight className="h-4 w-4 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-slate-500" />
                        </div>
                        <p className="mt-0.5 text-xs leading-relaxed text-slate-500">
                          {item.desc}
                        </p>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="flex h-[calc(100vh-5.5rem)] flex-col overflow-hidden rounded-2xl border border-white/80 bg-white/95 shadow-[0_8px_30px_rgba(15,23,42,0.06)] backdrop-blur animate-fade-up">
              {tab === "usage" && <MeUsagePanel />}
              {tab === "messages" && <MeMessagesPanel />}
              {tab === "mine" && <MePostsPanel />}
              {tab === "drafts" && <MeDraftsPanel />}
              {tab === "favorites" && <MeFavoritesPanel />}
              {tab === "mod" && isAdmin && <MeModPanel />}
            </div>
          )}
        </main>
      </div>
    </CommunityPageShell>
  );
}
