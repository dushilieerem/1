import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Activity,
  Bell,
  Bookmark,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  FilePenLine,
  FileText,
  Gauge,
  LayoutDashboard,
  Newspaper,
  Shield,
  UserRound,
  Users,
  X,
} from "lucide-react";
import { getStoredUser, prepareAuthHandoff } from "@/lib/auth";
import { getMyAgentUsage, type AgentUsageMe } from "@/lib/agentApi";
import { useConfirm } from "@/components/ConfirmDialog";
import {
  clearBrowseHistory,
  listBrowseHistory,
  removeBrowseHistoryItem,
  type BrowseKind,
} from "@/lib/browseHistory";
import { getNews, type NewsItem } from "@/lib/newsApi";
import {
  getCommunityPost,
  type CommunityPost,
} from "@/lib/communityApi";
import { NewsFeedCard } from "@/components/NewsFeedCard";
import { PageJump } from "@/components/PageJump";
import {
  AuthorAvatar,
  CommunityPageShell,
  PostListItem,
} from "@/components/community/communityUi";
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
  | "news-history"
  | "community-history"
  | "mod";

const TAB_IDS: MeTab[] = [
  "workspace",
  "usage",
  "messages",
  "mine",
  "drafts",
  "favorites",
  "news-history",
  "community-history",
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
  { id: "news-history", label: "资讯浏览历史", icon: Newspaper },
  { id: "community-history", label: "社区浏览历史", icon: Users },
  { id: "mod", label: "管理仓", icon: Shield, adminOnly: true },
];

/** 知识库独立站（可用 VITE_KH_URL 覆盖） */
const KH_URL =
  (import.meta.env.VITE_KH_URL as string | undefined)?.trim() ||
  "http://192.168.3.32:9531/";

const QUICK_LINKS: {
  id: MeTab;
  title: string;
  icon: typeof Bell;
  iconWrap: string;
  card: string;
}[] = [
  {
    id: "messages",
    title: "消息中心",
    icon: Bell,
    iconWrap: "bg-sky-500 text-white shadow-sky-200/80",
    card: "from-sky-50/90 to-white hover:border-sky-200",
  },
  {
    id: "mine",
    title: "我的发帖",
    icon: FileText,
    iconWrap: "bg-violet-500 text-white shadow-violet-200/80",
    card: "from-violet-50/90 to-white hover:border-violet-200",
  },
  {
    id: "drafts",
    title: "草稿箱",
    icon: FilePenLine,
    iconWrap: "bg-amber-500 text-white shadow-amber-200/80",
    card: "from-amber-50/90 to-white hover:border-amber-200",
  },
  {
    id: "favorites",
    title: "我的收藏",
    icon: Bookmark,
    iconWrap: "bg-emerald-500 text-white shadow-emerald-200/80",
    card: "from-emerald-50/90 to-white hover:border-emerald-200",
  },
  {
    id: "news-history",
    title: "资讯浏览历史",
    icon: Newspaper,
    iconWrap: "bg-rose-500 text-white shadow-rose-200/80",
    card: "from-rose-50/90 to-white hover:border-rose-200",
  },
  {
    id: "community-history",
    title: "社区浏览历史",
    icon: Users,
    iconWrap: "bg-indigo-500 text-white shadow-indigo-200/80",
    card: "from-indigo-50/90 to-white hover:border-indigo-200",
  },
];

const HISTORY_PAGE_SIZE = 10;

function MeBrowseHistoryPanel({
  kind,
  title,
  emptyHint,
}: {
  kind: BrowseKind;
  title: string;
  emptyHint: string;
}) {
  const confirm = useConfirm();
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [histTotal, setHistTotal] = useState(0);
  const [newsItems, setNewsItems] = useState<NewsItem[]>([]);
  const [posts, setPosts] = useState<CommunityPost[]>([]);
  const [missing, setMissing] = useState(0);

  const totalPages = Math.max(1, Math.ceil(histTotal / HISTORY_PAGE_SIZE));
  const pageSafe = Math.min(page, totalPages);

  const refresh = async (pageNum: number) => {
    setLoading(true);
    const histAll = listBrowseHistory(kind);
    setHistTotal(histAll.length);
    const tp = Math.max(1, Math.ceil(histAll.length / HISTORY_PAGE_SIZE));
    const p = Math.min(Math.max(1, pageNum), tp);
    if (p !== pageNum) setPage(p);
    const slice = histAll.slice(
      (p - 1) * HISTORY_PAGE_SIZE,
      p * HISTORY_PAGE_SIZE,
    );
    if (slice.length === 0) {
      setNewsItems([]);
      setPosts([]);
      setMissing(0);
      setLoading(false);
      return;
    }
    if (kind === "news") {
      const settled = await Promise.all(
        slice.map((h) =>
          getNews(h.id)
            .then((it) => ({ ok: true as const, it }))
            .catch(() => ({ ok: false as const })),
        ),
      );
      const ok = settled.filter((x) => x.ok).map((x) => x.it);
      setNewsItems(ok);
      setPosts([]);
      setMissing(settled.length - ok.length);
    } else {
      const settled = await Promise.all(
        slice.map((h) =>
          getCommunityPost(Number(h.id), { bump: false })
            .then((r) => ({ ok: true as const, post: r.post }))
            .catch(() => ({ ok: false as const })),
        ),
      );
      const ok = settled.filter((x) => x.ok).map((x) => x.post);
      setPosts(ok);
      setNewsItems([]);
      setMissing(settled.length - ok.length);
    }
    setLoading(false);
  };

  useEffect(() => {
    setPage(1);
  }, [kind]);

  useEffect(() => {
    void refresh(page);
  }, [kind, page]);

  const removeOne = async (id: number | string, label: string) => {
    const ok = await confirm({
      title: "移除浏览记录",
      message: `确认从历史中移除「${label}」？`,
      confirmLabel: "移除",
      danger: true,
    });
    if (!ok) return;
    removeBrowseHistoryItem(kind, id);
    const nextTotal = listBrowseHistory(kind).length;
    const nextPages = Math.max(1, Math.ceil(nextTotal / HISTORY_PAGE_SIZE));
    if (page > nextPages) setPage(nextPages);
    else void refresh(page);
  };

  const clearAll = async () => {
    const ok = await confirm({
      title: "清空浏览历史",
      message: `确认清空全部${kind === "news" ? "资讯" : "社区"}浏览记录？`,
      confirmLabel: "清空",
      danger: true,
    });
    if (!ok) return;
    clearBrowseHistory(kind);
    setPage(1);
    void refresh(1);
  };

  const empty = !loading && histTotal === 0;
  const hasItems = histTotal > 0;

  const pager =
    !loading && histTotal > HISTORY_PAGE_SIZE ? (
      <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
        <button
          type="button"
          disabled={pageSafe <= 1 || loading}
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronLeft className="h-4 w-4" />
          上一页
        </button>
        <span className="px-2 text-sm tabular-nums text-slate-600">
          {pageSafe} / {totalPages}
        </span>
        <button
          type="button"
          disabled={pageSafe >= totalPages || loading}
          onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          下一页
          <ChevronRight className="h-4 w-4" />
        </button>
        <PageJump page={pageSafe} totalPages={totalPages} onJump={setPage} />
      </div>
    ) : null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b border-slate-100 px-5 py-4">
        <h1 className="text-base font-semibold text-slate-900">{title}</h1>
        {hasItems ? (
          <span className="text-xs text-slate-400">
            共 {histTotal} 条
            {totalPages > 1 ? ` · 第 ${pageSafe}/${totalPages} 页` : ""}
          </span>
        ) : null}
        {hasItems ? (
          <button
            type="button"
            onClick={() => void clearAll()}
            className="ml-auto text-xs text-slate-400 hover:text-rose-600"
          >
            清空
          </button>
        ) : null}
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-5">
        {loading ? (
          <p className="py-16 text-center text-sm text-slate-400">加载中…</p>
        ) : empty ? (
          <p className="py-16 text-center text-sm text-slate-400">{emptyHint}</p>
        ) : kind === "news" ? (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              {newsItems.map((it) => (
                <div key={it.id} className="relative min-w-0">
                  <button
                    type="button"
                    title="从历史中移除"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      void removeOne(it.id, it.title);
                    }}
                    className="absolute right-3 top-3 z-10 inline-flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-white/95 text-slate-400 shadow-sm transition hover:border-rose-300 hover:bg-rose-50 hover:text-rose-600"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                  <NewsFeedCard item={it} />
                </div>
              ))}
            </div>
            {missing > 0 ? (
              <p className="pt-3 text-center text-[11px] text-slate-400">
                本页 {missing} 条已失效或无法加载
              </p>
            ) : null}
            {pager}
          </>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              {posts.map((p) => (
                <div
                  key={p.id}
                  className="relative min-w-0 overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm"
                >
                  <button
                    type="button"
                    title="从历史中移除"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      void removeOne(p.id, p.title);
                    }}
                    className="absolute right-2 top-2 z-10 inline-flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-white/95 text-slate-400 shadow-sm transition hover:border-rose-300 hover:bg-rose-50 hover:text-rose-600"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                  <PostListItem post={p} />
                </div>
              ))}
            </div>
            {missing > 0 ? (
              <p className="pt-3 text-center text-[11px] text-slate-400">
                本页 {missing} 条已失效或无法加载
              </p>
            ) : null}
            {pager}
          </>
        )}
      </div>
    </div>
  );
}

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

          <nav className="flex-1 space-y-1 overflow-y-auto p-2.5">
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
                  <Icon
                    className={`h-4 w-4 shrink-0 ${active ? "text-white" : "text-slate-400"}`}
                  />
                  <span className="leading-snug">{item.label}</span>
                </button>
              );
            })}
          </nav>

          {isAdmin ? (
            <div className="px-2.5 pb-2">
              <button
                type="button"
                onClick={() => {
                  prepareAuthHandoff();
                  window.open(KH_URL, "_blank", "noopener,noreferrer");
                }}
                className="flex w-full items-center gap-2.5 rounded-xl border border-sky-200 bg-sky-50 px-3 py-2.5 text-left text-sm font-medium text-sky-800 transition hover:bg-sky-100"
              >
                <BookOpen className="h-4 w-4 text-sky-600" />
                知识库平台
              </button>
            </div>
          ) : null}

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
                      className={`group flex items-center gap-3.5 rounded-2xl border border-slate-200/70 bg-gradient-to-br p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md ${item.card}`}
                    >
                      <span
                        className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl shadow-md ${item.iconWrap}`}
                      >
                        <Icon className="h-5 w-5" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-sm font-semibold text-slate-900">
                            {item.title}
                          </p>
                          <ChevronRight className="h-4 w-4 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-slate-500" />
                        </div>
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
              {tab === "news-history" && (
                <MeBrowseHistoryPanel
                  kind="news"
                  title="资讯浏览历史"
                  emptyHint="打开资讯详情后会出现在这里"
                />
              )}
              {tab === "community-history" && (
                <MeBrowseHistoryPanel
                  kind="community"
                  title="社区浏览历史"
                  emptyHint="打开社区帖子后会出现在这里"
                />
              )}
              {tab === "mod" && isAdmin && <MeModPanel />}
            </div>
          )}
        </main>
      </div>
    </CommunityPageShell>
  );
}
