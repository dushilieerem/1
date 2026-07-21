import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Eye, MessageCircle, PenLine, Star } from "lucide-react";
import { getStoredUser } from "@/lib/auth";
import {
  SECTION_META,
  excerpt,
  formatPostTime,
  listCommunityPosts,
  listHotPosts,
  type CommunityPost,
} from "@/lib/communityApi";

function avatarLetter(post: CommunityPost) {
  const name = post.author.display_name || post.author.username || "?";
  return name.slice(0, 1).toUpperCase();
}

function sectionBadge(section: string) {
  const map: Record<string, string> = {
    official: "bg-sky-50 text-sky-700",
    strategy: "bg-violet-50 text-violet-700",
    factor: "bg-emerald-50 text-emerald-700",
    qa: "bg-amber-50 text-amber-700",
    hotspot: "bg-orange-50 text-orange-700",
  };
  return map[section] ?? "bg-slate-100 text-slate-600";
}

/** 社区 Feed：主栏列表 + 右侧热门，对齐常见量化社区信息架构 */
export function CommunityFeedPage() {
  const navigate = useNavigate();
  const [section, setSection] = useState<string>("all");
  const [items, setItems] = useState<CommunityPost[]>([]);
  const [hot, setHot] = useState<CommunityPost[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(null);
    void listCommunityPosts({ section, limit: 50 })
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
  }, [section]);

  useEffect(() => {
    let cancelled = false;
    void listHotPosts(10)
      .then((data) => {
        if (!cancelled) setHot(data.items);
      })
      .catch(() => {
        if (!cancelled) setHot([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const officialPinned = useMemo(
    () => (section === "all" ? items.filter((p) => p.section === "official").slice(0, 5) : []),
    [items, section],
  );

  const feedItems = useMemo(() => {
    if (section !== "all" || officialPinned.length === 0) return items;
    const pinnedIds = new Set(officialPinned.map((p) => p.id));
    return items.filter((p) => !pinnedIds.has(p.id));
  }, [items, section, officialPinned]);

  const goNew = () => {
    if (!getStoredUser()) {
      navigate(`/login?next=${encodeURIComponent("/community/new")}`);
      return;
    }
    navigate("/community/new");
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-[#f3f5f8]">
      <div className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[1180px] flex-col gap-4 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 flex-1 flex-col gap-3 lg:flex-row lg:items-center lg:gap-8">
            <h1 className="shrink-0 text-xl font-bold tracking-tight text-slate-900">
              SVQuant 社区
            </h1>
            <nav className="flex flex-wrap items-center gap-1">
              {SECTION_META.map((s) => {
                const active = section === s.id;
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => setSection(s.id)}
                    className={`rounded px-3 py-1.5 text-sm transition ${
                      active
                        ? "font-semibold text-red-600"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    {s.label}
                    {active ? (
                      <span className="mt-0.5 block h-0.5 rounded-full bg-red-500" />
                    ) : (
                      <span className="mt-0.5 block h-0.5" />
                    )}
                  </button>
                );
              })}
            </nav>
          </div>
          <button
            type="button"
            onClick={goNew}
            className="inline-flex shrink-0 items-center justify-center gap-1.5 rounded bg-red-500 px-4 py-2 text-sm font-semibold text-white hover:bg-red-400"
          >
            <PenLine className="h-4 w-4" />
            发布帖子
          </button>
        </div>
      </div>

      <div className="mx-auto grid max-w-[1180px] gap-4 px-5 py-5 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="min-w-0 space-y-4">
          {err && (
            <div className="rounded border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-600">
              {err}
            </div>
          )}

          {officialPinned.length > 0 && (
            <section className="rounded border border-slate-200 bg-white px-4 py-3 shadow-sm shadow-slate-200/40">
              <div className="mb-2 flex items-center gap-2">
                <span className="rounded bg-sky-500 px-1.5 py-0.5 text-[11px] font-semibold text-white">
                  置顶
                </span>
                <span className="text-xs text-slate-400">官方公告</span>
              </div>
              <ul className="divide-y divide-slate-100">
                {officialPinned.map((post) => (
                  <li key={post.id}>
                    <Link
                      to={`/community/post/${post.id}`}
                      className="flex items-baseline justify-between gap-4 py-2.5 text-sm hover:text-red-600"
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
            </section>
          )}

          <section className="overflow-hidden rounded border border-slate-200 bg-white shadow-sm shadow-slate-200/40">
            <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
              <span className="text-sm font-medium text-slate-700">最新发布</span>
              <span className="text-xs text-slate-400">
                {loading ? "加载中…" : `共 ${total} 篇`}
              </span>
            </div>

            {!loading && !err && feedItems.length === 0 && (
              <div className="px-4 py-16 text-center">
                <p className="text-base font-medium text-slate-800">还没有帖子</p>
                <p className="mt-1 text-sm text-slate-500">来写第一条吧</p>
                <button
                  type="button"
                  onClick={goNew}
                  className="mt-5 rounded bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
                >
                  写第一帖
                </button>
              </div>
            )}

            <ul className="divide-y divide-slate-100">
              {feedItems.map((post) => (
                <li key={post.id}>
                  <Link
                    to={`/community/post/${post.id}`}
                    className="block px-4 py-4 transition hover:bg-slate-50/80"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${sectionBadge(post.section)}`}
                      >
                        {post.section_label}
                      </span>
                      <h2 className="text-[15px] font-semibold text-slate-900 hover:text-red-600">
                        {post.title}
                      </h2>
                    </div>
                    <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-slate-500">
                      {excerpt(post.body || post.code_snippet || "", 160)}
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-200 text-[10px] font-semibold text-slate-600">
                          {avatarLetter(post)}
                        </span>
                        {post.author.display_name || post.author.username || "匿名"}
                      </span>
                      <span>发布于 {formatPostTime(post.created_at)}</span>
                      <span className="inline-flex items-center gap-1">
                        <Eye className="h-3.5 w-3.5" />
                        {post.view_count}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <MessageCircle className="h-3.5 w-3.5" />
                        {post.comment_count ?? 0}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <Star className="h-3.5 w-3.5" />
                        {post.favorite_count ?? 0}
                      </span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        </div>

        <aside className="space-y-4">
          <section className="rounded border border-slate-200 bg-white p-4 shadow-sm shadow-slate-200/40">
            <h2 className="text-sm font-bold text-slate-900">热门帖子</h2>
            <p className="mt-0.5 text-[11px] text-slate-400">按浏览量</p>
            <ol className="mt-3 space-y-2.5">
              {hot.length === 0 && (
                <li className="text-xs text-slate-400">暂无数据</li>
              )}
              {hot.map((post, i) => (
                <li key={post.id}>
                  <Link
                    to={`/community/post/${post.id}`}
                    className="flex gap-2 text-sm leading-snug text-slate-700 hover:text-red-600"
                  >
                    <span
                      className={`w-4 shrink-0 text-xs font-bold ${
                        i < 3 ? "text-orange-500" : "text-slate-300"
                      }`}
                    >
                      {i + 1}
                    </span>
                    <span className="line-clamp-2">{post.title}</span>
                  </Link>
                </li>
              ))}
            </ol>
          </section>

          <section className="rounded border border-slate-200 bg-white p-4 shadow-sm shadow-slate-200/40">
            <h2 className="text-sm font-bold text-slate-900">分区</h2>
            <ul className="mt-3 space-y-1">
              {SECTION_META.filter((s) => s.id !== "all").map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => setSection(s.id)}
                    className={`flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-sm ${
                      section === s.id
                        ? "bg-red-50 font-medium text-red-600"
                        : "text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    {s.label}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>
    </div>
  );
}
