import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Loader2, UserCheck, UserPlus } from "lucide-react";
import { getStoredUser, subscribeAuth } from "@/lib/auth";
import {
  followUser,
  getUserProfile,
  listUserFollows,
  unfollowUser,
  type FollowListUser,
  type UserProfile,
} from "@/lib/profileApi";
import {
  AuthorAvatar,
  CommunityPageShell,
  CommunityPanel,
  PrimaryButton,
} from "@/components/community/communityUi";

function formatCount(n: number) {
  if (n >= 10000) return `${(n / 10000).toFixed(1).replace(/\.0$/, "")} 万`;
  return String(n);
}

export function CommunityProfileFollowsPage({
  kind,
}: {
  kind: "following" | "followers";
}) {
  const { username = "" } = useParams();
  const navigate = useNavigate();
  const [viewer, setViewer] = useState(() => getStoredUser());
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [items, setItems] = useState<FollowListUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [ownerBusy, setOwnerBusy] = useState(false);

  useEffect(() => subscribeAuth(() => setViewer(getStoredUser())), []);

  useEffect(() => {
    if (!username) return;
    let cancelled = false;
    setLoading(true);
    setErr(null);
    void Promise.all([
      getUserProfile(username),
      listUserFollows(username, kind, { limit: 50 }),
    ])
      .then(([p, list]) => {
        if (cancelled) return;
        setProfile(p.profile);
        setItems(list.items);
      })
      .catch((ex) => {
        if (cancelled) return;
        setErr(ex instanceof Error ? ex.message : String(ex));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [username, kind]);

  const onToggle = async (u: FollowListUser) => {
    if (u.is_self) return;
    if (!viewer) {
      navigate(`/login?next=/u/${encodeURIComponent(username)}/${kind}`);
      return;
    }
    setBusyId(u.id);
    try {
      const fn = u.is_following ? unfollowUser : followUser;
      await fn(u.username);
      setItems((prev) =>
        prev.map((x) =>
          x.id === u.id ? { ...x, is_following: !x.is_following } : x,
        ),
      );
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusyId(null);
    }
  };

  const onToggleOwner = async () => {
    if (!profile || profile.is_self) return;
    if (!viewer) {
      navigate(`/login?next=/u/${encodeURIComponent(profile.username)}/${kind}`);
      return;
    }
    setOwnerBusy(true);
    try {
      const fn = profile.is_following ? unfollowUser : followUser;
      const data = await fn(profile.username);
      setProfile(data.profile);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setOwnerBusy(false);
    }
  };

  const owner =
    profile?.display_name || profile?.username || username || "用户";
  const base = `/u/${encodeURIComponent(profile?.username || username)}`;

  return (
    <CommunityPageShell>
      <div className="mx-auto max-w-[1180px] px-5 py-6 pb-16 sm:py-8">
        {loading && !profile ? (
          <div className="flex items-center justify-center gap-2 py-24 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            加载中…
          </div>
        ) : err && !profile ? (
          <CommunityPanel className="px-6 py-12 text-center text-sm text-red-600">
            {err}
          </CommunityPanel>
        ) : profile ? (
          <div className="space-y-4">
            {/* 顶栏资料卡 · 对齐知乎主页头 */}
            <div className="rounded-2xl border border-slate-200/80 bg-white shadow-sm">
              <div className="relative h-32 overflow-hidden rounded-t-2xl bg-gradient-to-br from-slate-700 via-slate-600 to-slate-800 sm:h-40">
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
              <div className="px-5 pb-5 sm:px-7">
                <div className="flex flex-wrap items-end gap-4">
                  <div className="relative z-10 -mt-10 shrink-0 sm:-mt-12">
                    <Link to={base}>
                      <AuthorAvatar
                        name={owner}
                        src={profile.avatar_url}
                        size="xl"
                        className="!ring-4 !ring-white shadow-md"
                      />
                    </Link>
                  </div>
                  <div className="min-w-0 flex-1 pb-1 pt-2">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="min-w-0">
                        <Link
                          to={base}
                          className="text-xl font-bold tracking-tight text-slate-900 hover:text-red-600"
                        >
                          {owner}
                        </Link>
                        {profile.headline ? (
                          <p className="mt-1 line-clamp-1 text-sm text-slate-500">
                            {profile.headline}
                          </p>
                        ) : (
                          <p className="mt-1 text-xs text-slate-400">
                            @{profile.username}
                          </p>
                        )}
                      </div>
                      <div className="flex shrink-0 flex-wrap gap-2">
                        {profile.is_self ? (
                          <Link
                            to={`${base}/edit`}
                            className="inline-flex h-9 items-center rounded-lg border border-slate-200 bg-white px-3.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                          >
                            编辑资料
                          </Link>
                        ) : (
                          <PrimaryButton
                            type="button"
                            disabled={ownerBusy}
                            onClick={() => void onToggleOwner()}
                            className={
                              profile.is_following
                                ? "!h-9 !bg-slate-100 !px-3.5 !text-sm !text-slate-700 !shadow-none hover:!bg-slate-200"
                                : "!h-9 !px-3.5 !text-sm"
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
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_280px] lg:items-start">
              {/* 主栏 */}
              <div className="min-w-0 overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm">
                {/* 一级 Tab：动态 / 关注 */}
                <div className="flex border-b border-slate-100 px-2 sm:px-4">
                  <Link
                    to={base}
                    className="relative px-4 py-3.5 text-sm font-medium text-slate-500 transition hover:text-slate-800"
                  >
                    动态
                    <span className="ml-1 tabular-nums text-slate-400">
                      {profile.post_count}
                    </span>
                  </Link>
                  <Link
                    to={`${base}/following`}
                    className="relative px-4 py-3.5 text-sm font-semibold text-red-600"
                  >
                    关注
                    <span className="ml-1 font-normal tabular-nums text-red-400">
                      {profile.following_count + profile.followers_count}
                    </span>
                    <span className="absolute inset-x-4 bottom-0 h-0.5 rounded-full bg-red-500" />
                  </Link>
                </div>

                {/* 二级：关注了 / 关注者 */}
                <div className="flex gap-5 border-b border-slate-50 px-5 pt-3 sm:px-6">
                  <Link
                    to={`${base}/following`}
                    className={`pb-2.5 text-sm transition ${
                      kind === "following"
                        ? "border-b-2 border-red-500 font-semibold text-slate-900"
                        : "border-b-2 border-transparent text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    关注了 {profile.following_count} 人
                  </Link>
                  <Link
                    to={`${base}/followers`}
                    className={`pb-2.5 text-sm transition ${
                      kind === "followers"
                        ? "border-b-2 border-red-500 font-semibold text-slate-900"
                        : "border-b-2 border-transparent text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    关注者 {profile.followers_count} 人
                  </Link>
                </div>

                {loading ? (
                  <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-400">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    加载列表…
                  </div>
                ) : items.length === 0 ? (
                  <p className="px-5 py-16 text-center text-sm text-slate-400">
                    {kind === "following" ? "还没有关注任何人" : "还没有粉丝"}
                  </p>
                ) : (
                  <ul>
                    {items.map((u) => {
                      const name = u.display_name || u.username;
                      const posts = u.post_count ?? 0;
                      const fans = u.followers_count ?? 0;
                      return (
                        <li
                          key={u.id}
                          className="flex items-start gap-3.5 border-b border-slate-50 px-5 py-4 last:border-0 sm:px-6"
                        >
                          <Link
                            to={`/u/${encodeURIComponent(u.username)}`}
                            className="mt-0.5 shrink-0"
                          >
                            <AuthorAvatar
                              name={name}
                              src={u.avatar_url}
                              size="lg"
                              className="!ring-0"
                            />
                          </Link>
                          <div className="min-w-0 flex-1">
                            <Link
                              to={`/u/${encodeURIComponent(u.username)}`}
                              className="text-[15px] font-semibold text-slate-900 hover:text-red-600"
                            >
                              {name}
                            </Link>
                            <p className="mt-0.5 line-clamp-1 text-sm text-slate-500">
                              {u.headline?.trim() || `@${u.username}`}
                            </p>
                            <p className="mt-1.5 text-xs tabular-nums text-slate-400">
                              {formatCount(posts)} 帖子
                              <span className="mx-1.5 text-slate-200">·</span>
                              {formatCount(fans)} 关注者
                            </p>
                          </div>
                          {!u.is_self ? (
                            <button
                              type="button"
                              disabled={busyId === u.id}
                              onClick={() => void onToggle(u)}
                              className={`mt-1 inline-flex h-8 shrink-0 items-center gap-1 rounded-full px-3.5 text-xs font-semibold transition disabled:opacity-50 ${
                                u.is_following
                                  ? "border border-slate-200 bg-white text-slate-500 hover:bg-slate-50"
                                  : "bg-red-500 text-white shadow-sm shadow-red-200/50 hover:bg-red-400"
                              }`}
                            >
                              {u.is_following ? (
                                "已关注"
                              ) : (
                                <>
                                  <UserPlus className="h-3.5 w-3.5" />
                                  关注
                                </>
                              )}
                            </button>
                          ) : (
                            <span className="mt-1 inline-flex h-8 items-center rounded-full bg-slate-50 px-3 text-xs text-slate-400">
                              我
                            </span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
                {err ? (
                  <p className="border-t border-slate-50 px-5 py-2 text-xs text-red-600">
                    {err}
                  </p>
                ) : null}
              </div>

              {/* 侧栏 · 对齐知乎关注数字卡 */}
              <aside className="space-y-4">
                <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
                  <div className="grid grid-cols-2 gap-3 text-center">
                    <Link
                      to={`${base}/following`}
                      className="rounded-xl px-2 py-3 transition hover:bg-slate-50"
                    >
                      <p className="text-xl font-bold tabular-nums text-slate-900">
                        {profile.following_count}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">关注了</p>
                    </Link>
                    <Link
                      to={`${base}/followers`}
                      className="rounded-xl px-2 py-3 transition hover:bg-slate-50"
                    >
                      <p className="text-xl font-bold tabular-nums text-slate-900">
                        {profile.followers_count}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">关注者</p>
                    </Link>
                  </div>
                </div>

                <Link
                  to={base}
                  className="block rounded-2xl border border-slate-200/80 bg-white px-5 py-3.5 text-center text-sm font-semibold text-red-600 shadow-sm transition hover:bg-slate-50 hover:text-red-500"
                >
                  回到主页 →
                </Link>
              </aside>
            </div>
          </div>
        ) : null}
      </div>
    </CommunityPageShell>
  );
}
