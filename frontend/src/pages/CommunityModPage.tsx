import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Eye, Pin, Trash2 } from "lucide-react";
import { getStoredUser } from "@/lib/auth";
import { useConfirm } from "@/components/ConfirmDialog";
import { getAdminAgentUsage, type AgentUsageAdmin } from "@/lib/agentApi";
import {
  formatPostTime,
  listModerationPosts,
  moderateCommunityPost,
  purgeCommunityPost,
  type CommunityPost,
  type ModerationKind,
} from "@/lib/communityApi";
import {
  CommunityBackLink,
  CommunityPageShell,
  CommunityPanel,
  SectionPill,
} from "@/components/community/communityUi";

const TABS: { id: ModerationKind; label: string }[] = [
  { id: "hidden", label: "已下架" },
  { id: "pinned", label: "已置顶" },
];

export function CommunityModPage() {
  const navigate = useNavigate();
  const confirm = useConfirm();
  const [user] = useState(() => getStoredUser());
  const [kind, setKind] = useState<ModerationKind>("hidden");
  const [items, setItems] = useState<CommunityPost[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [agentUsage, setAgentUsage] = useState<AgentUsageAdmin | null>(null);

  const reload = useCallback(async (k: ModerationKind) => {
    setLoading(true);
    setErr(null);
    try {
      const data = await listModerationPosts({ kind: k, limit: 50 });
      setItems(data.items);
      setTotal(data.total);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!user) {
      navigate(`/login?next=${encodeURIComponent("/community/mod")}`, {
        replace: true,
      });
      return;
    }
    if (user.role !== "admin") {
      navigate("/community", { replace: true });
      return;
    }
    void reload(kind);
    void getAdminAgentUsage(7)
      .then(setAgentUsage)
      .catch(() => setAgentUsage(null));
  }, [user, kind, navigate, reload]);

  const onRestore = async (post: CommunityPost) => {
    const ok = await confirm({
      title: "恢复帖子",
      message: `确认恢复「${post.title}」？恢复后将重新出现在社区 Feed。`,
      confirmLabel: "恢复",
    });
    if (!ok) return;
    setBusyId(post.id);
    setErr(null);
    try {
      await moderateCommunityPost(post.id, { status: "published" });
      await reload(kind);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusyId(null);
    }
  };

  const onUnpin = async (post: CommunityPost) => {
    const ok = await confirm({
      title: "取消置顶",
      message: `确认取消「${post.title}」的置顶？`,
      confirmLabel: "取消置顶",
    });
    if (!ok) return;
    setBusyId(post.id);
    setErr(null);
    try {
      await moderateCommunityPost(post.id, { pinned: false });
      await reload(kind);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusyId(null);
    }
  };

  const onPurge = async (post: CommunityPost) => {
    const ok = await confirm({
      title: "彻底删除",
      message: `彻底删除「${post.title}」？评论与收藏一并清除，且不可恢复。`,
      confirmLabel: "彻底删除",
      danger: true,
    });
    if (!ok) return;
    setBusyId(post.id);
    setErr(null);
    try {
      await purgeCommunityPost(post.id);
      await reload(kind);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <CommunityPageShell>
      <div className="mx-auto max-w-[880px] px-5 py-6 animate-fade-up">
        <CommunityBackLink to="/community/me" label="返回个人主页" />
        <div className="mt-4">
          <p className="text-xs font-medium tracking-wide text-red-500/90">
            MODERATION
          </p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">
            管理仓
          </h1>
        </div>

        {agentUsage && (
          <CommunityPanel className="mt-4 px-5 py-4">
            <p className="text-[11px] font-medium tracking-wide text-red-500/90">
              SVQUANT AGENT · 近 {agentUsage.days} 日用量
            </p>
            <p className="mt-1 text-sm text-slate-700">
              调用 {agentUsage.totals.calls} 次 · 用户{" "}
              {agentUsage.totals.users} · token 约{" "}
              {agentUsage.totals.tokens_in + agentUsage.totals.tokens_out}
            </p>
            {agentUsage.by_user.length > 0 && (
              <ul className="mt-2 space-y-0.5 text-xs text-slate-500">
                {agentUsage.by_user.slice(0, 5).map((u) => (
                  <li key={u.user_id}>
                    {u.username} · {u.calls} 次
                  </li>
                ))}
              </ul>
            )}
          </CommunityPanel>
        )}

        <nav className="mt-5 flex gap-1 border-b border-slate-200" aria-label="管理分类">
          {TABS.map((t) => {
            const active = kind === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setKind(t.id)}
                className={`relative px-4 py-2.5 text-sm transition ${
                  active
                    ? "font-semibold text-red-600"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {t.label}
                <span
                  className={`absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-red-500 ${
                    active ? "opacity-100" : "opacity-0"
                  }`}
                />
              </button>
            );
          })}
        </nav>

        <p className="mt-3 text-sm text-slate-500">
          {loading ? "加载中…" : `共 ${total} 篇`}
        </p>

        {err && (
          <p className="mt-3 rounded-xl border border-red-100 bg-white px-4 py-3 text-sm text-red-600">
            {err}
          </p>
        )}

        {!loading && !err && items.length === 0 && (
          <CommunityPanel className="mt-4 px-5 py-14 text-center">
            <p className="text-base font-medium text-slate-800">
              {kind === "hidden" ? "暂无下架帖" : "暂无置顶帖"}
            </p>
            <p className="mt-1 text-sm text-slate-500">
              {kind === "hidden"
                ? "在帖子详情点「下架」后会出现在这里"
                : "在帖子详情点「置顶」后会出现在这里"}
            </p>
          </CommunityPanel>
        )}

        {items.length > 0 && (
          <CommunityPanel className="mt-4">
            <ul className="divide-y divide-slate-100">
              {items.map((post) => {
                const busy = busyId === post.id;
                const author =
                  post.author.display_name || post.author.username || "匿名";
                return (
                  <li
                    key={post.id}
                    className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <SectionPill
                          section={post.section}
                          label={post.section_label}
                        />
                        {post.is_pinned ? (
                          <span className="rounded bg-sky-500 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                            置顶
                          </span>
                        ) : null}
                        <Link
                          to={`/community/post/${post.id}`}
                          className="truncate text-sm font-semibold text-slate-900 hover:text-red-600"
                        >
                          {post.title}
                        </Link>
                      </div>
                      <p className="mt-1.5 text-xs text-slate-400">
                        {author} · {formatPostTime(post.updated_at || post.created_at)}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-2">
                      <Link
                        to={`/community/post/${post.id}`}
                        className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                      >
                        <Eye className="h-3.5 w-3.5" />
                        打开
                      </Link>
                      {kind === "hidden" ? (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void onRestore(post)}
                          className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100 disabled:opacity-60"
                        >
                          <Eye className="h-3.5 w-3.5" />
                          恢复
                        </button>
                      ) : (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void onUnpin(post)}
                          className="inline-flex items-center gap-1 rounded-lg border border-sky-200 bg-sky-50 px-2.5 py-1.5 text-xs font-medium text-sky-800 hover:bg-sky-100 disabled:opacity-60"
                        >
                          <Pin className="h-3.5 w-3.5" />
                          取消置顶
                        </button>
                      )}
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void onPurge(post)}
                        className="inline-flex items-center gap-1 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-60"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        彻底删除
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </CommunityPanel>
        )}
      </div>
    </CommunityPageShell>
  );
}
