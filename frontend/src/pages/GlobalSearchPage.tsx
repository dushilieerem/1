import { FormEvent, useEffect, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  Newspaper,
  Search,
  Users,
} from "lucide-react";
import {
  SECTION_META,
  formatPostTime,
  listCommunityPosts,
  type CommunityPost,
} from "@/lib/communityApi";
import {
  formatNewsWhen,
  listNews,
  type NewsItem,
} from "@/lib/newsApi";
import { NEWS_CATEGORIES } from "@/data/nav";
import {
  AuthorAvatar,
  SectionPill,
} from "@/components/community/communityUi";
import { PagerBar } from "@/components/PageJump";

const PAGE_SIZE = 10;

/** 正文摘要：去掉 HTML / Markdown，避免把标签原文露出来 */
function plainSnippet(raw: string | null | undefined, max = 100) {
  let t = raw || "";
  if (typeof document !== "undefined" && /<[a-z][\s\S]*>/i.test(t)) {
    const el = document.createElement("div");
    el.innerHTML = t;
    t = el.textContent || el.innerText || "";
  } else {
    t = t
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<[^>]+>/g, " ");
  }
  t = t
    .replace(/&nbsp;/gi, " ")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&amp;/gi, "&")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
    .replace(/\[[^\]]*\]\([^)]*\)/g, " ")
    .replace(/[#>*_`~|-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!t) return "";
  return t.length > max ? `${t.slice(0, max)}…` : t;
}

function Highlight({ text, q }: { text: string; q: string }) {
  if (!q) return <>{text}</>;
  const parts = text.split(
    new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"),
  );
  return (
    <>
      {parts.map((part, i) =>
        part.toLowerCase() === q.toLowerCase() ? (
          <mark key={i} className="rounded-sm bg-amber-100 px-0.5 text-inherit">
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}

function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium transition ${
        active
          ? "bg-slate-900 text-white"
          : "bg-white text-slate-600 ring-1 ring-slate-200 hover:ring-slate-300"
      }`}
    >
      {children}
    </button>
  );
}

/** 全局搜索一期：社区帖 + 资讯（复用 list API 的 q=） */
export function GlobalSearchPage() {
  const [params, setParams] = useSearchParams();
  const qFromUrl = (params.get("q") || "").trim();
  const [draft, setDraft] = useState(qFromUrl);

  const [postSection, setPostSection] = useState("all");
  const [postPage, setPostPage] = useState(1);
  const [posts, setPosts] = useState<CommunityPost[]>([]);
  const [postTotal, setPostTotal] = useState(0);
  const [postLoading, setPostLoading] = useState(false);

  const [newsCat, setNewsCat] = useState("all");
  const [newsPage, setNewsPage] = useState(1);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [newsTotal, setNewsTotal] = useState(0);
  const [newsLoading, setNewsLoading] = useState(false);

  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setDraft(qFromUrl);
    setPostSection("all");
    setPostPage(1);
    setNewsCat("all");
    setNewsPage(1);
  }, [qFromUrl]);

  useEffect(() => {
    if (!qFromUrl) {
      setPosts([]);
      setPostTotal(0);
      setPostLoading(false);
      return;
    }
    let cancelled = false;
    setPostLoading(true);
    setErr(null);
    void listCommunityPosts({
      q: qFromUrl,
      section: postSection,
      sort: "newest",
      limit: PAGE_SIZE,
      offset: (postPage - 1) * PAGE_SIZE,
    })
      .then((c) => {
        if (cancelled) return;
        setPosts(c.items || []);
        setPostTotal(c.total || 0);
      })
      .catch((ex) => {
        if (cancelled) return;
        setErr(ex instanceof Error ? ex.message : String(ex));
        setPosts([]);
        setPostTotal(0);
      })
      .finally(() => {
        if (!cancelled) setPostLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [qFromUrl, postSection, postPage]);

  useEffect(() => {
    if (!qFromUrl) {
      setNews([]);
      setNewsTotal(0);
      setNewsLoading(false);
      return;
    }
    let cancelled = false;
    setNewsLoading(true);
    setErr(null);
    const isFlash = newsCat === "flash";
    void listNews({
      q: qFromUrl,
      category: isFlash ? "all" : newsCat,
      mode: isFlash ? "flash" : "feed",
      limit: PAGE_SIZE,
      offset: (newsPage - 1) * PAGE_SIZE,
    })
      .then((n) => {
        if (cancelled) return;
        setNews(n.items || []);
        setNewsTotal(n.total || 0);
      })
      .catch((ex) => {
        if (cancelled) return;
        setErr(ex instanceof Error ? ex.message : String(ex));
        setNews([]);
        setNewsTotal(0);
      })
      .finally(() => {
        if (!cancelled) setNewsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [qFromUrl, newsCat, newsPage]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const next = draft.trim();
    if (!next) return;
    setParams({ q: next }, { replace: false });
  };

  const loading = postLoading || newsLoading;
  const emptyBoth =
    !loading && !err && qFromUrl && postTotal === 0 && newsTotal === 0;
  const postPages = Math.max(1, Math.ceil(postTotal / PAGE_SIZE));
  const newsPages = Math.max(1, Math.ceil(newsTotal / PAGE_SIZE));

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-[linear-gradient(180deg,#f8fafc_0%,#f1f5f9_40%,#eef2f7_100%)]">
      <div className="border-b border-slate-200/80 bg-white/95 shadow-sm shadow-slate-900/5">
        <div className="mx-auto max-w-[1440px] px-3 py-3 sm:px-5 lg:px-6 lg:py-4">
          <div className="flex items-center gap-2">
            <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-red-50 text-red-600 ring-1 ring-red-100">
              <Search className="h-3.5 w-3.5" />
            </span>
            <h1 className="text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">
              全局搜索
            </h1>
          </div>

          <form onSubmit={onSubmit} className="mt-3 flex gap-2">
            <div className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                type="search"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="搜社区帖、资讯…"
                className="w-full rounded-xl border border-slate-200 bg-slate-50/80 py-2.5 pl-10 pr-3 text-sm outline-none transition focus:border-red-300 focus:bg-white focus:ring-2 focus:ring-red-100 sm:py-3"
                autoFocus
              />
            </div>
            <button
              type="submit"
              className="shrink-0 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 sm:px-5 sm:py-3"
            >
              搜索
            </button>
          </form>
        </div>
      </div>

      <div className="mx-auto max-w-[1440px] px-3 py-3 sm:px-5 sm:py-4 lg:px-6">
        {!qFromUrl ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:max-w-2xl">
            {[
              {
                t: "社区帖",
                d: "策略分享、因子笔记、问答",
                icon: Users,
                tone: "text-red-600 bg-red-50",
              },
              {
                t: "资讯",
                d: "多源新闻标题与正文",
                icon: Newspaper,
                tone: "text-rose-700 bg-rose-50",
              },
            ].map((x) => (
              <div
                key={x.t}
                className="rounded-2xl border border-slate-200/80 bg-white/90 p-4 shadow-sm"
              >
                <span
                  className={`inline-flex h-8 w-8 items-center justify-center rounded-lg ${x.tone}`}
                >
                  <x.icon className="h-4 w-4" />
                </span>
                <p className="mt-2 text-sm font-semibold text-slate-900">{x.t}</p>
                <p className="mt-0.5 text-xs text-slate-500">{x.d}</p>
              </div>
            ))}
          </div>
        ) : null}

        {err ? (
          <p className="rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-600">
            {err}
          </p>
        ) : null}

        {qFromUrl && loading && posts.length === 0 && news.length === 0 ? (
          <div className="grid gap-4 lg:grid-cols-2">
            {[0, 1].map((k) => (
              <div
                key={k}
                className="h-72 animate-pulse rounded-2xl border border-slate-200/80 bg-white/80"
              />
            ))}
          </div>
        ) : null}

        {emptyBoth ? (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-white py-14 text-center">
            <p className="text-sm font-medium text-slate-600">
              未找到与「{qFromUrl}」相关的内容
            </p>
          </div>
        ) : null}

        {qFromUrl && !err && !emptyBoth ? (
          <div className="grid items-start gap-3 lg:grid-cols-2 lg:gap-4">
            {/* 社区：分区筛选 + 列表区可滚动 */}
            <section className="flex flex-col overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
              <div className="flex items-center justify-between gap-2 border-b border-slate-100 bg-gradient-to-r from-red-50/80 to-white px-3 py-2.5 sm:px-4">
                <h2 className="inline-flex items-center gap-2 text-sm font-bold text-slate-900">
                  <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-red-100 text-red-600">
                    <Users className="h-3.5 w-3.5" />
                  </span>
                  社区帖
                  <span className="rounded-md bg-white px-1.5 py-0.5 text-[11px] font-semibold text-slate-500 ring-1 ring-slate-200">
                    {postTotal}
                  </span>
                </h2>
                <Link
                  to={`/community?q=${encodeURIComponent(qFromUrl)}`}
                  className="inline-flex items-center gap-0.5 text-xs font-medium text-red-600 hover:underline"
                >
                  全部 <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </div>

              <div className="flex gap-1.5 overflow-x-auto border-b border-slate-100 bg-slate-50/50 px-3 py-2 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                {SECTION_META.map((s) => (
                  <FilterChip
                    key={s.id}
                    active={postSection === s.id}
                    onClick={() => {
                      setPostSection(s.id);
                      setPostPage(1);
                    }}
                  >
                    {s.label}
                  </FilterChip>
                ))}
              </div>

              <div className="max-h-[min(62vh,560px)] min-h-[220px] overflow-y-auto overscroll-contain">
                {postLoading && posts.length === 0 ? (
                  <p className="px-4 py-12 text-center text-sm text-slate-400">加载中…</p>
                ) : posts.length === 0 ? (
                  <p className="px-4 py-12 text-center text-sm text-slate-400">无匹配帖子</p>
                ) : (
                  <ul className="divide-y divide-slate-100">
                    {posts.map((p) => {
                      const name =
                        p.author.display_name || p.author.username || "用户";
                      const snip = plainSnippet(p.body);
                      return (
                        <li key={p.id}>
                          <Link
                            to={`/community/post/${p.id}`}
                            className="group block px-3 py-3 transition hover:bg-slate-50/90 sm:px-4 sm:py-3.5"
                          >
                            <div className="flex items-start gap-3">
                              <AuthorAvatar
                                name={name}
                                src={p.author.avatar_url}
                                size="md"
                                className="mt-0.5"
                              />
                              <div className="min-w-0 flex-1">
                                <div className="mb-1 flex flex-wrap items-center gap-1.5">
                                  <SectionPill
                                    section={p.section}
                                    label={p.section_label}
                                  />
                                  {p.is_pinned ? (
                                    <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 ring-1 ring-amber-100">
                                      置顶
                                    </span>
                                  ) : null}
                                </div>
                                <p className="text-sm font-semibold leading-snug text-slate-900 group-hover:text-red-700">
                                  <Highlight text={p.title} q={qFromUrl} />
                                </p>
                                {snip ? (
                                  <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-slate-500">
                                    {snip}
                                  </p>
                                ) : null}
                                <p className="mt-1.5 text-[11px] text-slate-400">
                                  {name} · {formatPostTime(p.created_at)}
                                </p>
                              </div>
                            </div>
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>

              {postTotal > 0 ? (
                <div className="border-t border-slate-100 bg-slate-50/60">
                  <PagerBar
                    page={postPage}
                    totalPages={postPages}
                    disabled={postLoading}
                    onJump={setPostPage}
                  />
                </div>
              ) : null}
            </section>

            {/* 资讯：分类筛选 + 分页 */}
            <section className="flex flex-col overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
              <div className="flex items-center justify-between gap-2 border-b border-slate-100 bg-gradient-to-r from-rose-50/80 to-white px-3 py-2.5 sm:px-4">
                <h2 className="inline-flex items-center gap-2 text-sm font-bold text-slate-900">
                  <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-rose-100 text-rose-700">
                    <Newspaper className="h-3.5 w-3.5" />
                  </span>
                  资讯
                  <span className="rounded-md bg-white px-1.5 py-0.5 text-[11px] font-semibold text-slate-500 ring-1 ring-slate-200">
                    {newsTotal}
                  </span>
                </h2>
                <Link
                  to={`/news?q=${encodeURIComponent(qFromUrl)}`}
                  className="inline-flex items-center gap-0.5 text-xs font-medium text-rose-700 hover:underline"
                >
                  全部 <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </div>

              <div className="flex gap-1.5 overflow-x-auto border-b border-slate-100 bg-slate-50/50 px-3 py-2 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                {NEWS_CATEGORIES.map((c) => (
                  <FilterChip
                    key={c.id}
                    active={newsCat === c.id}
                    onClick={() => {
                      setNewsCat(c.id);
                      setNewsPage(1);
                    }}
                  >
                    {c.label}
                  </FilterChip>
                ))}
              </div>

              <div className="max-h-[min(62vh,560px)] min-h-[220px] overflow-y-auto overscroll-contain">
                {newsLoading && news.length === 0 ? (
                  <p className="px-4 py-12 text-center text-sm text-slate-400">加载中…</p>
                ) : news.length === 0 ? (
                  <p className="px-4 py-12 text-center text-sm text-slate-400">无匹配资讯</p>
                ) : (
                  <ul className="divide-y divide-slate-100">
                    {news.map((it) => {
                      const snip = plainSnippet(it.summary, 110);
                      return (
                        <li key={it.id}>
                          <Link
                            to={`/news/${it.id}`}
                            className="group block px-3 py-3 transition hover:bg-rose-50/40 sm:px-4 sm:py-3.5"
                          >
                            <div className="mb-1.5 flex flex-wrap items-center gap-2 text-[11px]">
                              <span className="rounded-full bg-slate-900 px-2 py-0.5 font-semibold text-white">
                                {it.sourceLabel}
                              </span>
                              {it.isFlash ? (
                                <span className="rounded-full bg-amber-50 px-2 py-0.5 font-medium text-amber-800 ring-1 ring-amber-100">
                                  快讯
                                </span>
                              ) : null}
                              <span className="text-slate-400">
                                {formatNewsWhen(it.publishedAt)}
                              </span>
                            </div>
                            <p className="text-sm font-semibold leading-snug text-slate-900 group-hover:text-rose-700">
                              <Highlight text={it.title} q={qFromUrl} />
                            </p>
                            {snip ? (
                              <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-slate-500">
                                {snip}
                              </p>
                            ) : null}
                            {it.symbols?.length ? (
                              <div className="mt-2 flex flex-wrap gap-1">
                                {it.symbols.slice(0, 3).map((s) => (
                                  <span
                                    key={s}
                                    className="rounded bg-rose-50 px-1.5 py-0.5 text-[10px] font-medium text-rose-700"
                                  >
                                    {s}
                                  </span>
                                ))}
                              </div>
                            ) : null}
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>

              {newsTotal > 0 ? (
                <div className="border-t border-slate-100 bg-slate-50/60">
                  <PagerBar
                    page={newsPage}
                    totalPages={newsPages}
                    disabled={newsLoading}
                    onJump={setNewsPage}
                  />
                </div>
              ) : null}
            </section>
          </div>
        ) : null}
      </div>
    </div>
  );
}
