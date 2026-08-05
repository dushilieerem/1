import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  UserPlus,
  UserCheck,
  Pencil,
  Loader2,
  CalendarDays,
  PenLine,
  LayoutDashboard,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { getStoredUser, subscribeAuth } from "@/lib/auth";
import {
  followUser,
  getUserProfile,
  listUserPosts,
  unfollowUser,
  type UserProfile,
} from "@/lib/profileApi";
import {
  SECTION_META,
  type CommunityPost,
  type CommunitySection,
} from "@/lib/communityApi";
import {
  AuthorAvatar,
  CommunityPageShell,
  CommunityPanel,
  PostListItem,
  PrimaryButton,
  SectionDot,
} from "@/components/community/communityUi";
import { PageJump } from "@/components/PageJump";

const PAGE_SIZE = 10;

function formatJoined(iso?: string | null) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月加入`;
}

function normalizeSection(raw: string | null): string {
  if (!raw || raw === "all") return "all";
  if (SECTION_META.some((s) => s.id === raw)) return raw;
  return "all";
}

export function CommunityProfilePage() {
  const { username = "" } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const section = normalizeSection(searchParams.get("section"));
  const page = Math.max(1, Number(searchParams.get("page") || "1") || 1);

  const [viewer, setViewer] = useState(() => getStoredUser());
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [posts, setPosts] = useState<CommunityPost[]>([]);
  const [total, setTotal] = useState(0);
  const [sectionCounts, setSectionCounts] = useState<Record<string, number>>(
    {},
  );
  const [loading, setLoading] = useState(true);
  const [listLoading, setListLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [followBusy, setFollowBusy] = useState(false);

  useEffect(() => subscribeAuth(() => setViewer(getStoredUser())), []);

  useEffect(() => {
    if (!username) return;
    let cancelled = false;
    setLoading(true);
    setErr(null);
    void getUserProfile(username)
      .then((p) => {
        if (!cancelled) setProfile(p.profile);
      })
      .catch((ex) => {
        if (cancelled) return;
        setErr(ex instanceof Error ? ex.message : String(ex));
        setProfile(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [username]);

  useEffect(() => {
    if (!username) return;
    let cancelled = false;
    setListLoading(true);
    void listUserPosts(username, {
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
      section,
    })
      .then((list) => {
        if (cancelled) return;
        setPosts(list.items);
        setTotal(list.total);
        setSectionCounts(list.section_counts || {});
      })
      .catch((ex) => {
        if (cancelled) return;
        setErr(ex instanceof Error ? ex.message : String(ex));
        setPosts([]);
        setTotal(0);
      })
      .finally(() => {
        if (!cancelled) setListLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [username, section, page]);

  const sectionStats = useMemo(() => {
    return SECTION_META.filter(
      (s): s is (typeof SECTION_META)[number] & { id: CommunitySection } =>
        s.id !== "all" && (sectionCounts[s.id] || 0) > 0,
    ).map((s) => ({
      id: s.id as CommunitySection,
      label: s.label,
      count: sectionCounts[s.id] || 0,
    }));
  }, [sectionCounts]);

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const setSection = (id: string) => {
    const next = new URLSearchParams();
    if (id !== "all") next.set("section", id);
    setSearchParams(next, { replace: true });
  };

  const setPage = (p: number) => {
    const next = new URLSearchParams(searchParams);
    if (p <= 1) next.delete("page");
    else next.set("page", String(p));
    setSearchParams(next, { replace: true });
  };

  const onFollowToggle = async () => {
    if (!profile || profile.is_self) return;
    if (!viewer) {
      navigate(`/login?next=/u/${encodeURIComponent(profile.username)}`);
      return;
    }
    setFollowBusy(true);
    try {
      const fn = profile.is_following ? unfollowUser : followUser;
      const data = await fn(profile.username);
      setProfile(data.profile);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setFollowBusy(false);
    }
  };

  const display =
    profile?.display_name || profile?.username || username || "用户";
  const joined = formatJoined(profile?.created_at);
  const base = profile
    ? `/u/${encodeURIComponent(profile.username)}`
    : `/u/${encodeURIComponent(username)}`;

  return (
    <CommunityPageShell>
      <div className="mx-auto max-w-[1180px] px-5 py-6 pb-16 sm:py-8">
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-24 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            加载中…
          </div>
        ) : err && !profile ? (
          <CommunityPanel className="px-6 py-12 text-center">
            <p className="text-sm text-red-600">{err}</p>
            <Link
              to="/community"
              className="mt-4 inline-block text-sm font-medium text-slate-600 hover:text-red-600"
            >
              返回社区
            </Link>
          </CommunityPanel>
        ) : profile ? (
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px] lg:items-start">
            <div className="min-w-0 space-y-4">
              <div className="rounded-2xl border border-slate-200/80 bg-white shadow-sm">
                <div className="relative h-36 overflow-hidden rounded-t-2xl bg-gradient-to-br from-slate-700 via-slate-600 to-slate-800 sm:h-44">
                  {profile.cover_url ? (
                    <img
                      src={profile.cover_url}
                      alt=""
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <div
                      className="absolute inset-0 opacity-40"
                      style={{
                        backgroundImage:
                          "radial-gradient(circle at 20% 30%, rgba(248,113,113,0.35), transparent 45%), radial-gradient(circle at 80% 20%, rgba(56,189,248,0.25), transparent 40%)",
                      }}
                      aria-hidden
                    />
                  )}
                </div>

                <div className="px-5 pb-6 sm:px-7">
                  <div className="relative z-10 -mt-10 w-fit sm:-mt-12">
                    <AuthorAvatar
                      name={display}
                      src={profile.avatar_url}
                      size="xl"
                      className="!ring-4 !ring-white shadow-md"
                    />
                  </div>

                  <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
                    <h1 className="text-2xl font-bold tracking-tight text-slate-900">
                      {display}
                    </h1>
                    {profile.is_self ? (
                      <Link
                        to={`${base}/edit`}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:bg-white"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                        编辑个人资料
                      </Link>
                    ) : (
                      <PrimaryButton
                        type="button"
                        disabled={followBusy}
                        onClick={() => void onFollowToggle()}
                        className={
                          profile.is_following
                            ? "!bg-slate-100 !px-3 !py-1.5 !text-slate-700 !shadow-none hover:!bg-slate-200"
                            : "!px-3 !py-1.5"
                        }
                      >
                        {profile.is_following ? (
                          <>
                            <UserCheck className="h-4 w-4" />
                            已关注
                          </>
                        ) : (
                          <>
                            <UserPlus className="h-4 w-4" />
                            关注
                          </>
                        )}
                      </PrimaryButton>
                    )}
                  </div>

                  {profile.headline ? (
                    <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-slate-600">
                      {profile.headline}
                    </p>
                  ) : null}
                  <p className="mt-1 text-xs text-slate-400">
                    @{profile.username}
                  </p>

                  <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 border-t border-slate-100 pt-4 text-sm">
                    <Link
                      to={`${base}/following`}
                      className="hover:text-red-600"
                    >
                      <strong className="tabular-nums font-semibold text-slate-900">
                        {profile.following_count}
                      </strong>{" "}
                      <span className="text-slate-500">关注</span>
                    </Link>
                    <Link
                      to={`${base}/followers`}
                      className="hover:text-red-600"
                    >
                      <strong className="tabular-nums font-semibold text-slate-900">
                        {profile.followers_count}
                      </strong>{" "}
                      <span className="text-slate-500">粉丝</span>
                    </Link>
                    <span>
                      <strong className="tabular-nums font-semibold text-slate-900">
                        {profile.post_count}
                      </strong>{" "}
                      <span className="text-slate-500">帖子</span>
                    </span>
                  </div>

                  {profile.bio ? (
                    <p className="mt-4 max-w-2xl whitespace-pre-wrap text-sm leading-relaxed text-slate-600">
                      {profile.bio}
                    </p>
                  ) : null}
                  {err ? (
                    <p className="mt-2 text-sm text-red-600">{err}</p>
                  ) : null}
                </div>
              </div>

              <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm">
                <div className="border-b border-slate-100 px-5 py-3 sm:px-6">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h2 className="text-sm font-semibold text-slate-800">
                      动态
                      <span className="ml-2 font-normal tabular-nums text-slate-400">
                        {total}
                      </span>
                    </h2>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {SECTION_META.map((s) => {
                      const active = section === s.id;
                      const count =
                        s.id === "all"
                          ? Object.values(sectionCounts).reduce(
                              (a, b) => a + b,
                              0,
                            )
                          : sectionCounts[s.id] || 0;
                      if (s.id !== "all" && count === 0) return null;
                      return (
                        <button
                          key={s.id}
                          type="button"
                          onClick={() => setSection(s.id)}
                          className={`rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                            active
                              ? "bg-slate-900 text-white"
                              : "bg-slate-50 text-slate-600 hover:bg-slate-100"
                          }`}
                        >
                          {s.label}
                          {s.id !== "all" ? (
                            <span className="ml-1 tabular-nums opacity-70">
                              {count}
                            </span>
                          ) : null}
                        </button>
                      );
                    })}
                  </div>
                </div>
                {listLoading ? (
                  <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-400">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    加载动态…
                  </div>
                ) : posts.length === 0 ? (
                  <div className="px-5 py-14 text-center sm:px-6">
                    <p className="text-sm text-slate-400">
                      {section === "all"
                        ? "还没有发布内容"
                        : "该分区暂无内容"}
                    </p>
                    {profile.is_self && section === "all" ? (
                      <Link
                        to="/community/new"
                        className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-red-600 hover:text-red-500"
                      >
                        <PenLine className="h-4 w-4" />
                        去发第一帖
                      </Link>
                    ) : null}
                  </div>
                ) : (
                  <>
                    <div className="divide-y divide-slate-100">
                      {posts.map((p) => (
                        <PostListItem key={p.id} post={p} showAuthor={false} />
                      ))}
                    </div>
                    {pageCount > 1 ? (
                      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-5 py-3 sm:px-6">
                        <p className="text-xs text-slate-400">
                          第 {page} / {pageCount} 页 · 每页 {PAGE_SIZE} 条
                        </p>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <button
                            type="button"
                            disabled={page <= 1}
                            onClick={() => setPage(page - 1)}
                            className="inline-flex items-center gap-0.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 disabled:opacity-40 hover:bg-slate-50"
                          >
                            <ChevronLeft className="h-3.5 w-3.5" />
                            上一页
                          </button>
                          <button
                            type="button"
                            disabled={page >= pageCount}
                            onClick={() => setPage(page + 1)}
                            className="inline-flex items-center gap-0.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 disabled:opacity-40 hover:bg-slate-50"
                          >
                            下一页
                            <ChevronRight className="h-3.5 w-3.5" />
                          </button>
                          <PageJump
                            page={page}
                            totalPages={pageCount}
                            onJump={setPage}
                          />
                        </div>
                      </div>
                    ) : null}
                  </>
                )}
              </div>
            </div>

            <aside className="space-y-4">
              <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
                <h3 className="text-xs font-semibold tracking-wide text-slate-400">
                  关于
                </h3>
                {profile.bio ? (
                  <p className="mt-2 line-clamp-6 text-sm leading-relaxed text-slate-600">
                    {profile.bio}
                  </p>
                ) : (
                  <p className="mt-2 text-sm text-slate-400">
                    {profile.is_self
                      ? "还没有简介，编辑资料写一句吧。"
                      : "这位作者还没有填写简介。"}
                  </p>
                )}
                {joined ? (
                  <p className="mt-4 inline-flex items-center gap-1.5 text-xs text-slate-400">
                    <CalendarDays className="h-3.5 w-3.5" />
                    {joined}
                  </p>
                ) : null}
              </div>

              <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
                <h3 className="text-xs font-semibold tracking-wide text-slate-400">
                  创作分布
                </h3>
                {sectionStats.length === 0 ? (
                  <p className="mt-3 text-sm text-slate-400">暂无分区数据</p>
                ) : (
                  <ul className="mt-3 space-y-2.5">
                    {sectionStats.map((s) => (
                      <li key={s.id}>
                        <button
                          type="button"
                          onClick={() => setSection(s.id)}
                          className="flex w-full items-center justify-between gap-2 text-sm hover:text-red-600"
                        >
                          <span className="inline-flex items-center gap-2 text-slate-600">
                            <SectionDot sectionId={s.id} />
                            {s.label}
                          </span>
                          <span className="tabular-nums font-medium text-slate-800">
                            {s.count}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {profile.is_self ? (
                <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
                  <p className="mb-3 text-xs font-semibold tracking-wide text-slate-400">
                    快捷入口
                  </p>
                  <div className="space-y-1">
                    <Link
                      to="/community/me"
                      className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-slate-600 transition hover:bg-slate-50 hover:text-slate-900"
                    >
                      <LayoutDashboard className="h-4 w-4 text-slate-400" />
                      个人中心
                    </Link>
                    <Link
                      to="/community/new"
                      className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-slate-600 transition hover:bg-slate-50 hover:text-slate-900"
                    >
                      <PenLine className="h-4 w-4 text-slate-400" />
                      写新帖
                    </Link>
                  </div>
                </div>
              ) : (
                <div className="rounded-2xl border border-slate-200/80 bg-gradient-to-br from-slate-50 to-white p-5 shadow-sm">
                  <p className="text-sm font-medium text-slate-800">逛逛社区</p>
                  <p className="mt-1 text-xs leading-relaxed text-slate-500">
                    看看其他人在讨论什么策略与因子。
                  </p>
                  <Link
                    to="/community"
                    className="mt-3 inline-block text-sm font-semibold text-red-600 hover:text-red-500"
                  >
                    进入 Feed →
                  </Link>
                </div>
              )}
            </aside>
          </div>
        ) : null}
      </div>
    </CommunityPageShell>
  );
}
