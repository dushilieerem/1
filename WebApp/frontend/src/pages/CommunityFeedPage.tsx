import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bookmark, PenLine, UserRound } from "lucide-react";
import { getStoredUser } from "@/lib/auth";
import {
  SECTION_META,
  listCommunityPosts,
  listHotPosts,
  type CommunityPost,
} from "@/lib/communityApi";
import {
  CommunityPageShell,
  CommunityPanel,
  HotRankBadge,
  PostListItem,
  PrimaryButton,
  SectionDot,
} from "@/components/community/communityUi";

/** 社区 Feed：主栏列表 + 右侧热门 */
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
    <CommunityPageShell>
      <div className="border-b border-slate-200/80 bg-white/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-[1180px] flex-col gap-5 px-5 py-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="flex min-w-0 flex-1 flex-col gap-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-xs font-medium tracking-wide text-red-500/90">
                  COMMUNITY
                </p>
                <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">
                  SVQuant 社区
                </h1>
              </div>
              <div className="flex flex-wrap gap-2 text-xs">
                <Link
                  to="/community/favorites"
                  className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
                >
                  <Bookmark className="h-3.5 w-3.5" />
                  收藏
                </Link>
                <Link
                  to="/community/mine"
                  className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
                >
                  <UserRound className="h-3.5 w-3.5" />
                  我的
                </Link>
              </div>
            </div>
            <nav className="flex flex-wrap items-center gap-1">
              {SECTION_META.map((s) => {
                const active = section === s.id;
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => setSection(s.id)}
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
          </div>
          <PrimaryButton onClick={goNew} className="shrink-0 self-start lg:self-auto">
            <PenLine className="h-4 w-4" />
            发布帖子
          </PrimaryButton>
        </div>
      </div>

      <div className="mx-auto grid max-w-[1180px] gap-5 px-5 py-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="min-w-0 space-y-4 animate-fade-up">
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
                <span className="text-xs font-medium text-sky-800/70">官方公告</span>
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
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
              <span className="text-sm font-semibold text-slate-800">最新发布</span>
              <span className="text-xs text-slate-400">
                {loading ? "加载中…" : `共 ${total} 篇`}
              </span>
            </div>

            {!loading && !err && feedItems.length === 0 && (
              <div className="px-5 py-20 text-center">
                <p className="text-lg font-semibold text-slate-800">还没有帖子</p>
                <p className="mt-1.5 text-sm text-slate-500">分享一条策略思路或因子笔记吧</p>
                <PrimaryButton onClick={goNew} className="mt-6">
                  写第一帖
                </PrimaryButton>
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
            <p className="mt-0.5 text-[11px] text-slate-400">按浏览量</p>
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
