import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { PenLine, Search } from "lucide-react";
import { getStoredUser, subscribeAuth } from "@/lib/auth";
import {
  SECTION_META,
  listCommunityPosts,
  listHotPosts,
  type CommunityPost,
  type CommunityPostSort,
} from "@/lib/communityApi";
import {
  CommunityPageShell,
  CommunityPanel,
  HotRankBadge,
  PostListItem,
  PrimaryButton,
  SectionDot,
} from "@/components/community/communityUi";

const VALID_SECTIONS = new Set(SECTION_META.map((s) => s.id));

const SORT_OPTIONS: { id: CommunityPostSort; label: string }[] = [
  { id: "views", label: "浏览数最多" },
  { id: "favorites", label: "收藏数最多" },
  { id: "newest", label: "最新发布" },
];

function normalizeSection(raw: string | null): string {
  if (!raw || !VALID_SECTIONS.has(raw as (typeof SECTION_META)[number]["id"])) {
    return "all";
  }
  return raw;
}

function normalizeSort(raw: string | null): CommunityPostSort {
  if (raw === "favorites" || raw === "newest" || raw === "views") return raw;
  return "views";
}

/** 社区 Feed：主栏列表 + 右侧热门；分区 / 搜索 / 排序经 URL 同步 */
export function CommunityFeedPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const section = normalizeSection(searchParams.get("section"));
  const sort = normalizeSort(searchParams.get("sort"));
  const qFromUrl = (searchParams.get("q") || "").trim();
  const [qDraft, setQDraft] = useState(qFromUrl);
  const [items, setItems] = useState<CommunityPost[]>([]);
  const [hot, setHot] = useState<CommunityPost[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [user, setUser] = useState(() => getStoredUser());

  useEffect(() => subscribeAuth(() => setUser(getStoredUser())), []);

  const sectionLabel =
    SECTION_META.find((s) => s.id === section)?.label ?? "全部";

  useEffect(() => {
    setQDraft(qFromUrl);
  }, [qFromUrl]);

  const writeParams = (
    nextSection: string,
    nextQ: string,
    nextSort: CommunityPostSort = sort,
  ) => {
    const params: Record<string, string> = {};
    if (nextSection !== "all") params.section = nextSection;
    const qq = nextQ.trim();
    if (qq) params.q = qq;
    if (nextSort !== "views") params.sort = nextSort;
    setSearchParams(params, { replace: true });
  };

  const setSection = (id: string) => {
    writeParams(normalizeSection(id), qFromUrl, sort);
  };

  const setSort = (id: CommunityPostSort) => {
    writeParams(section, qFromUrl, id);
  };

  const submitSearch = (raw?: string) => {
    writeParams(section, (raw ?? qDraft).trim(), sort);
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(null);
    void listCommunityPosts({
      section,
      q: qFromUrl || undefined,
      sort,
      limit: 50,
    })
      .then((data) => {
        if (cancelled) return;
        setItems(data.items);
        setTotal(data.total);
      })
      .catch((ex) => {
        if (cancelled) return;
        setErr(ex instanceof Error ? ex.message : String(ex));
        setItems([]);
        setTotal(0);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [section, qFromUrl, sort]);

  useEffect(() => {
    let cancelled = false;
    void listHotPosts(10, section)
      .then((data) => {
        if (cancelled) return;
        const list =
          section === "all"
            ? data.items
            : data.items.filter((p) => p.section === section);
        setHot(list);
      })
      .catch(() => {
        if (!cancelled) setHot([]);
      });
    return () => {
      cancelled = true;
    };
  }, [section]);

  const officialPinned = useMemo(
    () =>
      !qFromUrl
        ? items.filter((p) => p.is_pinned).slice(0, 8)
        : [],
    [items, qFromUrl],
  );

  const feedItems = useMemo(() => {
    if (officialPinned.length === 0) return items;
    const pinnedIds = new Set(officialPinned.map((p) => p.id));
    return items.filter((p) => !pinnedIds.has(p.id));
  }, [items, officialPinned]);

  const goNew = () => {
    if (!getStoredUser()) {
      navigate(`/login?next=${encodeURIComponent("/community/new")}`);
      return;
    }
    const next =
      section !== "all"
        ? `/community/new?section=${encodeURIComponent(section)}`
        : "/community/new";
    navigate(next);
  };

  return (
    <CommunityPageShell>
      <div className="border-b border-slate-200/80 bg-white/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-[1180px] flex-col gap-5 px-5 py-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="flex min-w-0 flex-1 flex-col gap-4">
            <div>
              <p className="text-xs font-medium tracking-wide text-red-500/90">
                COMMUNITY
              </p>
              <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">
                SVQuant 社区
              </h1>
            </div>
            <nav className="flex flex-wrap items-center gap-1" aria-label="社区分区">
              {SECTION_META.map((s) => {
                const active = section === s.id;
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => setSection(s.id)}
                    aria-current={active ? "page" : undefined}
                    className={`relative rounded-lg px-3 py-2 text-sm transition ${
                      active
                        ? "font-semibold text-red-600"
                        : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                    }`}
                  >
                    {s.label}
                    <span
                      className={`community-tab-underline absolute inset-x-3 -bottom-0.5 h-0.5 rounded-full bg-red-500 ${
                        active ? "opacity-100" : "opacity-0"
                      }`}
                    />
                  </button>
                );
              })}
            </nav>
            <form
              className="flex max-w-xl items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                submitSearch();
              }}
            >
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  type="search"
                  value={qDraft}
                  onChange={(e) => setQDraft(e.target.value)}
                  placeholder="搜索标题、正文或代码…"
                  className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-red-300 focus:ring-2 focus:ring-red-100"
                />
              </div>
              <button
                type="submit"
                className="shrink-0 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
              >
                搜索
              </button>
              {qFromUrl ? (
                <button
                  type="button"
                  onClick={() => {
                    setQDraft("");
                    writeParams(section, "", sort);
                  }}
                  className="shrink-0 rounded-lg px-2 py-2 text-sm text-slate-500 transition hover:text-slate-800"
                >
                  清除
                </button>
              ) : null}
            </form>
          </div>
          <PrimaryButton onClick={goNew} className="shrink-0 self-start lg:self-auto">
            <PenLine className="h-4 w-4" />
            发布帖子
          </PrimaryButton>
        </div>
      </div>

      <div className="mx-auto grid max-w-[1180px] gap-5 px-5 py-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="min-w-0 space-y-4 animate-fade-up">
          {!user ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-100 bg-amber-50/80 px-4 py-3 text-sm text-amber-900">
              <span>游客可浏览帖子；发帖、评论、收藏、克隆需登录。</span>
              <Link
                to={`/login?next=${encodeURIComponent(
                  `/community${searchParams.toString() ? `?${searchParams}` : ""}`,
                )}`}
                className="shrink-0 font-semibold text-red-600 hover:underline"
              >
                去登录
              </Link>
            </div>
          ) : null}
          {err && (
            <div className="rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-600">
              {err}
            </div>
          )}

          {officialPinned.length > 0 && (
            <CommunityPanel className="border-l-4 border-l-sky-400">
              <div className="flex items-center gap-2 border-b border-slate-100 bg-sky-50/40 px-4 py-2.5">
                <span className="rounded-md bg-sky-500 px-1.5 py-0.5 text-[11px] font-semibold text-white">
                  置顶
                </span>
              </div>
              <ul className="divide-y divide-slate-100">
                {officialPinned.map((post) => (
                  <li key={post.id}>
                    <Link
                      to={`/community/post/${post.id}`}
                      className="flex items-baseline justify-between gap-4 px-4 py-3 text-sm transition hover:bg-sky-50/50 hover:text-red-600"
                    >
                      <span className="min-w-0 truncate font-medium text-slate-800">
                        {post.title}
                      </span>
                      <span className="shrink-0 text-xs text-slate-400">
                        {post.author.display_name || post.author.username}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </CommunityPanel>
          )}

          <CommunityPanel>
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-3">
              <div className="flex min-w-0 flex-wrap items-center gap-3">
                {qFromUrl || section !== "all" ? (
                  <span className="text-sm font-semibold text-slate-800">
                    {qFromUrl ? `搜索「${qFromUrl}」` : sectionLabel}
                  </span>
                ) : null}
                <div
                  className="flex items-center gap-1 rounded-lg bg-slate-50 p-0.5"
                  role="group"
                  aria-label="帖子排序"
                >
                  {SORT_OPTIONS.map((opt) => {
                    const active = sort === opt.id;
                    return (
                      <button
                        key={opt.id}
                        type="button"
                        onClick={() => setSort(opt.id)}
                        className={`rounded-md px-2.5 py-1 text-xs transition ${
                          active
                            ? "bg-white font-medium text-slate-800 shadow-sm"
                            : "text-slate-500 hover:text-slate-700"
                        }`}
                      >
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
              </div>
              <span className="text-xs text-slate-400">
                {loading ? "加载中…" : `共 ${total} 篇`}
              </span>
            </div>

            {!loading && !err && feedItems.length === 0 && (
              <div className="px-5 py-20 text-center">
                <p className="text-lg font-semibold text-slate-800">
                  {qFromUrl
                    ? "没有匹配的帖子"
                    : section === "all"
                      ? "还没有帖子"
                      : `「${sectionLabel}」暂无帖子`}
                </p>
                <p className="mt-1.5 text-sm text-slate-500">
                  {qFromUrl
                    ? "换个关键词试试，或清除搜索看全部"
                    : section === "all"
                      ? "分享一条策略思路或因子笔记吧"
                      : "换个分区看看，或发一篇到本分区"}
                </p>
                <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
                  {qFromUrl ? (
                    <button
                      type="button"
                      onClick={() => {
                        setQDraft("");
                        writeParams(section, "", sort);
                      }}
                      className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700 transition hover:bg-slate-50"
                    >
                      清除搜索
                    </button>
                  ) : null}
                  {section !== "all" && !qFromUrl && (
                    <button
                      type="button"
                      onClick={() => setSection("all")}
                      className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700 transition hover:bg-slate-50"
                    >
                      查看全部
                    </button>
                  )}
                  {!qFromUrl && (
                    <PrimaryButton onClick={goNew}>
                      {section === "all" ? "写第一帖" : "发到本分区"}
                    </PrimaryButton>
                  )}
                </div>
              </div>
            )}

            <ul className="divide-y divide-slate-100">
              {feedItems.map((post) => (
                <li key={post.id}>
                  <PostListItem post={post} />
                </li>
              ))}
            </ul>
          </CommunityPanel>
        </div>

        <aside className="space-y-4 animate-fade-up stagger-1">
          <CommunityPanel className="p-4">
            <h2 className="text-sm font-bold tracking-tight text-slate-900">热门帖子</h2>
            <p className="mt-0.5 text-[11px] text-slate-400">
              {section === "all" ? "全站 · 按浏览量" : `${sectionLabel} · 按浏览量`}
            </p>
            <ol className="mt-4 space-y-3">
              {hot.length === 0 && (
                <li className="text-xs text-slate-400">暂无数据</li>
              )}
              {hot.map((post, i) => (
                <li key={post.id}>
                  <Link
                    to={`/community/post/${post.id}`}
                    className="flex gap-2.5 text-sm leading-snug text-slate-700 transition hover:text-red-600"
                  >
                    <HotRankBadge rank={i + 1} />
                    <span className="line-clamp-2 pt-0.5">{post.title}</span>
                  </Link>
                </li>
              ))}
            </ol>
          </CommunityPanel>

          <CommunityPanel className="p-4">
            <h2 className="text-sm font-bold tracking-tight text-slate-900">分区</h2>
            <ul className="mt-3 space-y-1">
              {SECTION_META.filter((s) => s.id !== "all").map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => setSection(s.id)}
                    className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm transition ${
                      section === s.id
                        ? "bg-red-50 font-medium text-red-600"
                        : "text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    <SectionDot sectionId={s.id} />
                    {s.label}
                  </button>
                </li>
              ))}
            </ul>
          </CommunityPanel>
        </aside>
      </div>
    </CommunityPageShell>
  );
}
