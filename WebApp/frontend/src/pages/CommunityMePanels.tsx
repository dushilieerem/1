import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Activity,
  ArrowLeft,
  FilePenLine,
  PenLine,
  Eye,
  EyeOff,
  Flag,
  Pin,
  Sparkles,
  Trash2,
} from "lucide-react";
import ReactECharts from "echarts-for-react";
import { useConfirm } from "@/components/ConfirmDialog";
import {
  getAdminAgentUsage,
  getMyAgentUsage,
  setUserAgentQuota,
  type AgentUsageAdmin,
  type AgentUsageMe,
} from "@/lib/agentApi";
import {
  deleteCommunityPost,
  formatPostTime,
  getCommunityPost,
  listCommunityReports,
  listModerationPosts,
  listMyFavorites,
  listMyPosts,
  listNotifications,
  markNotificationsRead,
  moderateCommunityPost,
  purgeCommunityPost,
  resolveCommunityReport,
  unreadNotificationCount,
  type CommunityNotification,
  type CommunityPost,
  type CommunityReport,
  type ModerationKind,
  type NotificationType,
} from "@/lib/communityApi";
import {
  AuthorAvatar,
  PostListItem,
  PrimaryButton,
  SectionPill,
} from "@/components/community/communityUi";
import { MarkdownBody } from "@/components/community/MarkdownBody";

const MSG_TABS: { id: NotificationType; label: string }[] = [
  { id: "reply", label: "回复我的" },
  { id: "mention", label: "@我的" },
  { id: "like", label: "收到的赞" },
];

function typeLabel(t: NotificationType) {
  if (t === "reply") return "回复了你";
  if (t === "mention") return "在评论里 @了你";
  return "赞了你的评论";
}

function PanelChrome({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-slate-100 bg-gradient-to-r from-white to-rose-50/40 px-5 py-4 sm:px-6">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-slate-900">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
        </div>
        {actions}
      </div>
      <div className="min-h-0 flex-1 overflow-auto">{children}</div>
    </div>
  );
}

export function MeMessagesPanel() {
  const [tab, setTab] = useState<NotificationType>("reply");
  const [items, setItems] = useState<CommunityNotification[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async (typ: NotificationType) => {
    setLoading(true);
    setErr(null);
    try {
      const [list, unread] = await Promise.all([
        listNotifications({ type: typ, limit: 50 }),
        unreadNotificationCount(),
      ]);
      setItems(list.items);
      setCounts(unread.by_type || {});
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(tab);
  }, [tab, load]);

  const onOpen = async (n: CommunityNotification) => {
    if (!n.read_at) {
      try {
        const res = await markNotificationsRead({ ids: [n.id] });
        setCounts(res.by_type || {});
        setItems((prev) =>
          prev.map((x) =>
            x.id === n.id ? { ...x, read_at: new Date().toISOString() } : x,
          ),
        );
      } catch {
        // ignore
      }
    }
  };

  const markTabRead = async () => {
    try {
      const res = await markNotificationsRead({ type: tab });
      setCounts(res.by_type || {});
      setItems((prev) =>
        prev.map((x) => ({
          ...x,
          read_at: x.read_at || new Date().toISOString(),
        })),
      );
    } catch (ex) {
      window.alert(ex instanceof Error ? ex.message : String(ex));
    }
  };

  return (
    <PanelChrome
      title="消息中心"
      subtitle="点开一条后进入帖子详情"
      actions={
        <button
          type="button"
          onClick={() => void markTabRead()}
          className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-slate-500 transition hover:bg-white hover:text-red-600"
        >
          本栏标为已读
        </button>
      }
    >
      <nav className="flex gap-1 border-b border-slate-100 bg-white px-3">
        {MSG_TABS.map((t) => {
          const active = tab === t.id;
          const n = counts[t.id] || 0;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`relative px-3 py-3 text-sm transition ${
                active
                  ? "font-semibold text-red-600"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {t.label}
              {n > 0 && (
                <span className="ml-1.5 inline-flex min-w-[1.1rem] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">
                  {n > 99 ? "99+" : n}
                </span>
              )}
              {active && (
                <span className="absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-red-500" />
              )}
            </button>
          );
        })}
      </nav>

      {err && (
        <p className="mx-5 mt-4 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-600">
          {err}
        </p>
      )}

      {loading ? (
        <p className="px-5 py-16 text-center text-sm text-slate-400">加载中…</p>
      ) : items.length === 0 ? (
        <p className="px-5 py-16 text-center text-sm text-slate-400">暂无消息</p>
      ) : (
        <ul className="divide-y divide-slate-100 bg-white">
          {items.map((n) => {
            const actor = n.actor.display_name || n.actor.username || "用户";
            const href = `/community/post/${n.post_id}${
              n.comment_id ? `?comment=${n.comment_id}` : ""
            }`;
            return (
              <li key={n.id}>
                <Link
                  to={href}
                  onClick={() => void onOpen(n)}
                  className={`flex gap-3 px-5 py-4 transition hover:bg-rose-50/50 sm:px-6 ${
                    !n.read_at ? "bg-rose-50/40" : ""
                  }`}
                >
                  <AuthorAvatar name={actor} size="md" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-slate-800">
                      <span className="font-semibold">{actor}</span>{" "}
                      <span className="text-slate-600">{typeLabel(n.type)}</span>
                    </p>
                    {n.comment_body && (
                      <p className="mt-1 line-clamp-2 text-xs text-slate-500">
                        {n.comment_body}
                      </p>
                    )}
                    <p className="mt-1 text-[11px] text-slate-400">
                      {formatPostTime(n.created_at)}
                      {n.post_title ? ` · ${n.post_title}` : ""}
                    </p>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </PanelChrome>
  );
}

export function MePostsPanel() {
  const navigate = useNavigate();
  const [items, setItems] = useState<CommunityPost[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void listMyPosts({ limit: 50 })
      .then((data) => {
        if (cancelled) return;
        setItems(data.items);
        setTotal(data.total);
      })
      .catch((ex) => {
        if (!cancelled) setErr(ex instanceof Error ? ex.message : String(ex));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <PanelChrome
      title="我的发帖"
      subtitle={loading ? "加载中…" : `共 ${total} 篇 · 点击进入详情`}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to="/community/ai-assist"
            className="inline-flex items-center gap-1.5 rounded-xl bg-white px-3.5 py-2 text-xs font-semibold text-red-600 shadow-sm ring-1 ring-red-100 transition hover:bg-red-50"
          >
            <Sparkles className="h-3.5 w-3.5" />
            AI 发帖助手
          </Link>
          <PrimaryButton onClick={() => navigate("/community/new")}>
            <PenLine className="h-4 w-4" />
            发帖
          </PrimaryButton>
        </div>
      }
    >
      {err && (
        <p className="m-4 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-600">
          {err}
        </p>
      )}
      {!loading && !err && items.length === 0 ? (
        <div className="px-5 py-16 text-center">
          <p className="text-sm font-medium text-slate-800">还没有发过帖</p>
          <PrimaryButton onClick={() => navigate("/community/new")} className="mt-4">
            写第一帖
          </PrimaryButton>
        </div>
      ) : (
        <ul className="divide-y divide-slate-100 bg-white">
          {items.map((post) => (
            <li key={post.id}>
              <PostListItem post={post} showAuthor={false} />
            </li>
          ))}
        </ul>
      )}
    </PanelChrome>
  );
}

export function MeDraftsPanel() {
  const navigate = useNavigate();
  const confirm = useConfirm();
  const [items, setItems] = useState<CommunityPost[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const data = await listMyPosts({ status: "draft", limit: 50 });
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
    void reload();
  }, [reload]);

  const onDelete = async (post: CommunityPost) => {
    const ok = await confirm({
      title: "删除草稿",
      message: `确认删除草稿「${post.title}」？删除后不可恢复。`,
      confirmLabel: "删除",
      danger: true,
    });
    if (!ok) return;
    setBusyId(post.id);
    try {
      await deleteCommunityPost(post.id);
      await reload();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <PanelChrome
      title="草稿箱"
      subtitle={loading ? "加载中…" : `共 ${total} 篇 · 点「继续编辑」进入编辑页`}
      actions={
        <PrimaryButton onClick={() => navigate("/community/new")}>
          <FilePenLine className="h-4 w-4" />
          写新帖
        </PrimaryButton>
      }
    >
      {err && (
        <p className="m-4 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-600">
          {err}
        </p>
      )}
      {!loading && !err && items.length === 0 ? (
        <p className="px-5 py-16 text-center text-sm text-slate-400">暂无草稿</p>
      ) : (
        <ul className="divide-y divide-slate-100 bg-white">
          {items.map((post) => {
            const busy = busyId === post.id;
            return (
              <li
                key={post.id}
                className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <SectionPill section={post.section} label={post.section_label} />
                    <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 ring-1 ring-amber-100">
                      草稿
                    </span>
                    <Link
                      to={`/community/post/${post.id}/edit`}
                      className="truncate text-sm font-semibold text-slate-900 hover:text-red-600"
                    >
                      {post.title || "未命名草稿"}
                    </Link>
                  </div>
                  <p className="mt-1.5 text-xs text-slate-400">
                    更新于 {formatPostTime(post.updated_at || post.created_at)}
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  <Link
                    to={`/community/post/${post.id}/edit`}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    <FilePenLine className="h-3.5 w-3.5" />
                    继续编辑
                  </Link>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void onDelete(post)}
                    className="inline-flex items-center gap-1 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-60"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    删除
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </PanelChrome>
  );
}

export function MeFavoritesPanel() {
  const [items, setItems] = useState<CommunityPost[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void listMyFavorites({ limit: 50 })
      .then((data) => {
        if (cancelled) return;
        setItems(data.items);
        setTotal(data.total);
      })
      .catch((ex) => {
        if (!cancelled) setErr(ex instanceof Error ? ex.message : String(ex));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <PanelChrome
      title="我的收藏"
      subtitle={loading ? "加载中…" : `共 ${total} 篇 · 点击进入详情`}
    >
      {err && (
        <p className="m-4 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-600">
          {err}
        </p>
      )}
      {!loading && !err && items.length === 0 ? (
        <div className="px-5 py-16 text-center">
          <p className="text-sm text-slate-500">还没有收藏</p>
          <Link
            to="/community"
            className="mt-3 inline-block text-sm font-medium text-red-600 hover:underline"
          >
            去社区看看
          </Link>
        </div>
      ) : (
        <ul className="divide-y divide-slate-100 bg-white">
          {items.map((post) => (
            <li key={post.id}>
              <PostListItem post={post} />
            </li>
          ))}
        </ul>
      )}
    </PanelChrome>
  );
}

type ModTab = ModerationKind | "reports";
type ModSection = "posts" | "usage";

const MOD_SECTIONS: { id: ModSection; label: string }[] = [
  { id: "posts", label: "帖子管理" },
  { id: "usage", label: "各用户用量汇总" },
];

const MOD_TABS: { id: ModTab; label: string }[] = [
  { id: "reports", label: "举报" },
  { id: "hidden", label: "已下架" },
  { id: "pinned", label: "已置顶" },
];

export function MeModPanel() {
  const confirm = useConfirm();
  const [section, setSection] = useState<ModSection>("posts");
  const [kind, setKind] = useState<ModTab>("reports");
  const [items, setItems] = useState<CommunityPost[]>([]);
  const [reports, setReports] = useState<CommunityReport[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [agentUsage, setAgentUsage] = useState<AgentUsageAdmin | null>(null);
  const [usageLoading, setUsageLoading] = useState(false);
  const [quotaDrafts, setQuotaDrafts] = useState<Record<number, string>>({});
  const [quotaBusyId, setQuotaBusyId] = useState<number | null>(null);
  const [previewPost, setPreviewPost] = useState<CommunityPost | null>(null);
  const [previewReport, setPreviewReport] = useState<CommunityReport | null>(
    null,
  );
  const [previewLoading, setPreviewLoading] = useState(false);

  const reload = useCallback(async (k: ModTab) => {
    setLoading(true);
    setErr(null);
    try {
      if (k === "reports") {
        const data = await listCommunityReports({ status: "open", limit: 50 });
        setReports(data.items);
        setItems([]);
        setTotal(data.total);
      } else {
        const data = await listModerationPosts({ kind: k, limit: 50 });
        setItems(data.items);
        setReports([]);
        setTotal(data.total);
      }
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
      setItems([]);
      setReports([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, []);

  const reloadUsage = useCallback(async () => {
    setUsageLoading(true);
    setErr(null);
    try {
      const data = await getAdminAgentUsage(7);
      setAgentUsage(data);
      const drafts: Record<number, string> = {};
      for (const u of data.by_user) {
        drafts[u.user_id] = String(u.quota_daily ?? 200);
      }
      setQuotaDrafts(drafts);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
      setAgentUsage(null);
    } finally {
      setUsageLoading(false);
    }
  }, []);

  const onSaveQuota = async (userId: number, username: string) => {
    const raw = quotaDrafts[userId];
    const n = Number(raw);
    if (!Number.isFinite(n) || !Number.isInteger(n) || n < 0 || n > 100000) {
      setErr("日上限须为 0～100000 的整数");
      return;
    }
    const ok = await confirm({
      title: "修改日配额",
      message: `将「${username}」的每日 Agent 调用上限改为 ${n}？立即生效。`,
      confirmLabel: "保存",
    });
    if (!ok) return;
    setQuotaBusyId(userId);
    setErr(null);
    try {
      const res = await setUserAgentQuota(userId, n);
      setAgentUsage((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          by_user: prev.by_user.map((u) =>
            u.user_id === userId
              ? {
                  ...u,
                  quota_daily: res.user.quota_daily,
                  used_today: res.user.used_today,
                  remaining: res.user.remaining,
                }
              : u,
          ),
        };
      });
      setQuotaDrafts((d) => ({
        ...d,
        [userId]: String(res.user.quota_daily),
      }));
      await confirm({
        title: "更改成功",
        message: `「${username}」日上限已更新为 ${res.user.quota_daily}。`,
        confirmLabel: "知道了",
        alert: true,
      });
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setQuotaBusyId(null);
    }
  };

  useEffect(() => {
    if (section === "posts") {
      setPreviewPost(null);
      setPreviewReport(null);
      void reload(kind);
    } else {
      setPreviewPost(null);
      setPreviewReport(null);
      void reloadUsage();
    }
  }, [section, kind, reload, reloadUsage]);

  const openPostPreview = async (
    postId: number,
    report?: CommunityReport | null,
  ) => {
    setPreviewLoading(true);
    setErr(null);
    setPreviewReport(report || null);
    try {
      const data = await getCommunityPost(postId, { bump: false });
      setPreviewPost(data.post);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
      setPreviewPost(null);
      setPreviewReport(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  const closePreview = () => {
    setPreviewPost(null);
    setPreviewReport(null);
  };

  const onRestore = async (post: CommunityPost) => {
    const ok = await confirm({
      title: "恢复帖子",
      message: `确认恢复「${post.title}」？恢复后将重新出现在社区 Feed。`,
      confirmLabel: "恢复",
    });
    if (!ok) return;
    setBusyId(post.id);
    try {
      await moderateCommunityPost(post.id, { status: "published" });
      closePreview();
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
    try {
      await moderateCommunityPost(post.id, { pinned: false });
      closePreview();
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
    try {
      await purgeCommunityPost(post.id);
      closePreview();
      await reload(kind);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusyId(null);
    }
  };

  const onDismissReport = async (r: CommunityReport) => {
    const ok = await confirm({
      title: "忽略举报",
      message: "确认忽略该举报？将标记为已处理，不会下架内容。",
      confirmLabel: "忽略",
    });
    if (!ok) return;
    setBusyId(r.id);
    try {
      await resolveCommunityReport(r.id, "dismissed");
      closePreview();
      await reload("reports");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusyId(null);
    }
  };

  const onHideFromReport = async (r: CommunityReport) => {
    const ok = await confirm({
      title: "下架帖子",
      message: `确认下架「${r.post_title || `帖 #${r.post_id}`}」并标记该举报已处理？`,
      confirmLabel: "下架",
      danger: true,
    });
    if (!ok) return;
    setBusyId(r.id);
    try {
      await moderateCommunityPost(r.post_id, { status: "hidden" });
      await resolveCommunityReport(r.id, "resolved");
      closePreview();
      await reload("reports");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusyId(null);
    }
  };

  const emptyText =
    kind === "reports"
      ? "暂无待处理举报"
      : kind === "hidden"
        ? "暂无下架帖"
        : "暂无置顶帖";

  return (
    <PanelChrome title="管理仓">
      <div className="border-b border-slate-100 bg-white px-5 py-3 sm:px-6">
        <div className="flex flex-wrap gap-2">
          {MOD_SECTIONS.map((s) => {
            const active = section === s.id;
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => {
                  closePreview();
                  setSection(s.id);
                }}
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                  active
                    ? "border-red-200 bg-red-50 text-red-700"
                    : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50"
                }`}
              >
                {s.label}
              </button>
            );
          })}
        </div>
      </div>

      {err && (
        <p className="m-4 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-600">
          {err}
        </p>
      )}

      {section === "usage" ? (
        usageLoading ? (
          <p className="px-5 py-16 text-center text-sm text-slate-400">加载中…</p>
        ) : !agentUsage || agentUsage.by_user.length === 0 ? (
          <p className="px-5 py-16 text-center text-sm text-slate-400">
            暂无用户
          </p>
        ) : (
          <>
            <div className="border-b border-slate-100 bg-slate-50/80 px-5 py-3 text-sm text-slate-600 sm:px-6">
              近 {agentUsage.days} 日合计 {agentUsage.totals.calls} 次 · token 约{" "}
              {agentUsage.totals.tokens_in + agentUsage.totals.tokens_out}
            </div>
            <div className="overflow-x-auto px-3 py-3 sm:px-4">
              <table className="w-full min-w-[720px] border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    <th className="px-3 py-2.5 font-semibold normal-case">
                      用户
                    </th>
                    <th className="px-3 py-2.5 font-semibold normal-case">
                      近{agentUsage.days}日调用
                    </th>
                    <th className="px-3 py-2.5 font-semibold normal-case">
                      Token
                    </th>
                    <th className="px-3 py-2.5 font-semibold normal-case">
                      今日已用
                    </th>
                    <th className="px-3 py-2.5 font-semibold normal-case">
                      日上限
                    </th>
                    <th className="px-3 py-2.5 font-semibold normal-case">
                      操作
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {agentUsage.by_user.map((u) => {
                    const name =
                      (u.display_name && u.display_name.trim()) ||
                      u.username ||
                      `id-${u.user_id}`;
                    const draft = quotaDrafts[u.user_id] ?? String(u.quota_daily);
                    const dirty = Number(draft) !== Number(u.quota_daily);
                    const busy = quotaBusyId === u.user_id;
                    return (
                      <tr
                        key={u.user_id}
                        className="border-b border-slate-100 hover:bg-slate-50/80"
                      >
                        <td className="px-3 py-3 align-middle">
                          <p className="font-medium text-slate-900">{name}</p>
                          <p className="text-xs text-slate-400">
                            @{u.username}
                            {u.role === "admin" ? " · 管理员" : ""}
                          </p>
                        </td>
                        <td className="px-3 py-3 align-middle tabular-nums text-slate-700">
                          {u.calls}
                        </td>
                        <td className="px-3 py-3 align-middle tabular-nums text-slate-600">
                          {u.tokens_in + u.tokens_out}
                        </td>
                        <td className="px-3 py-3 align-middle tabular-nums text-slate-700">
                          {u.used_today}
                          <span className="text-slate-400">
                            {" "}
                            / {u.quota_daily}
                          </span>
                        </td>
                        <td className="px-3 py-3 align-middle">
                          <input
                            type="number"
                            min={0}
                            max={100000}
                            step={1}
                            value={draft}
                            disabled={busy}
                            onChange={(e) =>
                              setQuotaDrafts((d) => ({
                                ...d,
                                [u.user_id]: e.target.value,
                              }))
                            }
                            className="w-24 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm tabular-nums text-slate-800 outline-none focus:border-red-300 focus:ring-2 focus:ring-red-100 disabled:opacity-60"
                          />
                        </td>
                        <td className="px-3 py-3 align-middle">
                          <button
                            type="button"
                            disabled={busy || !dirty}
                            onClick={() => void onSaveQuota(u.user_id, name)}
                            className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            {busy ? "保存中…" : "保存"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )
      ) : previewLoading ? (
        <p className="px-5 py-16 text-center text-sm text-slate-400">加载帖子…</p>
      ) : previewPost ? (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-white px-4 py-3 sm:px-5">
            <button
              type="button"
              onClick={closePreview}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              返回管理仓
            </button>
            <div className="flex flex-wrap gap-2">
              {previewReport ? (
                <>
                  <button
                    type="button"
                    disabled={busyId === previewReport.id}
                    onClick={() => void onHideFromReport(previewReport)}
                    className="inline-flex items-center gap-1 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs font-medium text-amber-800 hover:bg-amber-100 disabled:opacity-60"
                  >
                    <EyeOff className="h-3.5 w-3.5" />
                    下架帖
                  </button>
                  <button
                    type="button"
                    disabled={busyId === previewReport.id}
                    onClick={() => void onDismissReport(previewReport)}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-60"
                  >
                    <Flag className="h-3.5 w-3.5" />
                    忽略举报
                  </button>
                </>
              ) : kind === "hidden" ? (
                <button
                  type="button"
                  disabled={busyId === previewPost.id}
                  onClick={() => void onRestore(previewPost)}
                  className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100 disabled:opacity-60"
                >
                  <Eye className="h-3.5 w-3.5" />
                  恢复
                </button>
              ) : kind === "pinned" ? (
                <button
                  type="button"
                  disabled={busyId === previewPost.id}
                  onClick={() => void onUnpin(previewPost)}
                  className="inline-flex items-center gap-1 rounded-lg border border-sky-200 bg-sky-50 px-2.5 py-1.5 text-xs font-medium text-sky-800 hover:bg-sky-100 disabled:opacity-60"
                >
                  <Pin className="h-3.5 w-3.5" />
                  取消置顶
                </button>
              ) : null}
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-6">
            <div className="flex flex-wrap items-center gap-2">
              <SectionPill
                section={previewPost.section}
                label={previewPost.section_label}
              />
              {previewPost.is_pinned ? (
                <span className="rounded bg-sky-500 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                  置顶
                </span>
              ) : null}
              {previewPost.status === "hidden" ? (
                <span className="rounded bg-amber-500 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                  已下架
                </span>
              ) : null}
            </div>
            <h3 className="mt-3 text-xl font-bold tracking-tight text-slate-900">
              {previewPost.title}
            </h3>
            <p className="mt-2 text-xs text-slate-400">
              {previewPost.author.display_name ||
                previewPost.author.username ||
                "匿名"}{" "}
              · {formatPostTime(previewPost.created_at)}
              {previewReport ? (
                <>
                  {" "}
                  · 举报原因{" "}
                  {previewReport.reason_label || previewReport.reason}
                </>
              ) : null}
            </p>
            {previewReport?.detail ? (
              <p className="mt-2 rounded-lg border border-amber-100 bg-amber-50/80 px-3 py-2 text-xs text-amber-900">
                举报说明：{previewReport.detail}
              </p>
            ) : null}
            <div className="mt-5 border-t border-slate-100 pt-5">
              <MarkdownBody source={previewPost.body || ""} />
            </div>
            {previewPost.code_snippet ? (
              <pre className="mt-4 overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
                {previewPost.code_snippet}
              </pre>
            ) : null}
          </div>
        </div>
      ) : (
        <>
          <nav className="flex gap-1 border-b border-slate-100 bg-white px-3">
            {MOD_TABS.map((t) => {
              const active = kind === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setKind(t.id)}
                  className={`relative px-3 py-3 text-sm transition ${
                    active
                      ? "font-semibold text-red-600"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {t.label}
                  {active && (
                    <span className="absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-red-500" />
                  )}
                </button>
              );
            })}
          </nav>

          {!loading &&
          !err &&
          (kind === "reports" ? reports.length === 0 : items.length === 0) ? (
            <p className="px-5 py-16 text-center text-sm text-slate-400">
              {emptyText}
            </p>
          ) : kind === "reports" ? (
            <ul className="divide-y divide-slate-100 bg-white">
              {reports.map((r) => {
                const busy = busyId === r.id;
                const reporter =
                  r.reporter?.display_name || r.reporter?.username || "匿名";
                return (
                  <li
                    key={r.id}
                    className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded bg-amber-500 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                          {r.target_type === "comment" ? "评论" : "帖子"}
                        </span>
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
                          {r.reason_label || r.reason}
                        </span>
                        <button
                          type="button"
                          onClick={() => void openPostPreview(r.post_id, r)}
                          className="truncate text-left text-sm font-semibold text-slate-900 hover:text-red-600"
                        >
                          {r.post_title || `帖 #${r.post_id}`}
                        </button>
                      </div>
                      {r.comment_body ? (
                        <p className="mt-1 line-clamp-2 text-xs text-slate-500">
                          评论：{r.comment_body}
                        </p>
                      ) : null}
                      {r.detail ? (
                        <p className="mt-1 text-xs text-slate-500">
                          说明：{r.detail}
                        </p>
                      ) : null}
                      <p className="mt-1.5 text-xs text-slate-400">
                        举报人 {reporter} · {formatPostTime(r.created_at)}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => void openPostPreview(r.post_id, r)}
                        className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                      >
                        <Eye className="h-3.5 w-3.5" />
                        打开
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void onHideFromReport(r)}
                        className="inline-flex items-center gap-1 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs font-medium text-amber-800 hover:bg-amber-100 disabled:opacity-60"
                      >
                        <EyeOff className="h-3.5 w-3.5" />
                        下架帖
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void onDismissReport(r)}
                        className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-60"
                      >
                        <Flag className="h-3.5 w-3.5" />
                        忽略
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <ul className="divide-y divide-slate-100 bg-white">
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
                        <button
                          type="button"
                          onClick={() => void openPostPreview(post.id)}
                          className="truncate text-left text-sm font-semibold text-slate-900 hover:text-red-600"
                        >
                          {post.title}
                        </button>
                      </div>
                      <p className="mt-1.5 text-xs text-slate-400">
                        {author} ·{" "}
                        {formatPostTime(post.updated_at || post.created_at)}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => void openPostPreview(post.id)}
                        className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                      >
                        <Eye className="h-3.5 w-3.5" />
                        打开
                      </button>
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
          )}
        </>
      )}
    </PanelChrome>
  );
}

const SKILL_LABELS: Record<string, string> = {
  polish_title: "润色标题",
  polish_body: "润色正文",
  audit_claims: "内容审校",
  strip_unverifiable: "按异议删改",
  suggest_section: "建议分区",
};

function skillLabel(skill: string) {
  return SKILL_LABELS[skill] || skill;
}

function fmtTokens(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

/** 个人中心 · AI 用量 */
export function MeUsagePanel() {
  const [days, setDays] = useState<1 | 7 | 30>(7);
  const [trendMode, setTrendMode] = useState<"calls" | "tokens">("calls");
  const [data, setData] = useState<AgentUsageMe | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    setErr(null);
    void getMyAgentUsage(days)
      .then(setData)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [days]);

  useEffect(() => {
    load();
  }, [load]);

  const usedPct = useMemo(() => {
    if (!data?.quota_daily) return 0;
    return Math.min(100, Math.round((data.used_today / data.quota_daily) * 100));
  }, [data]);

  const barWarn = usedPct >= 80;

  const totals = data?.totals || { calls: 0, runs: 0, tokens_in: 0, tokens_out: 0 };
  const tokenSum = totals.tokens_in + totals.tokens_out;
  const avgPerDay = days > 0 ? Math.round((totals.calls / days) * 10) / 10 : 0;

  const chartOpt = useMemo(() => {
    const rows = data?.by_day || [];
    const labels = rows.map((r) => r.day.slice(5));
    const values =
      trendMode === "calls"
        ? rows.map((r) => r.calls)
        : rows.map((r) => r.tokens_in + r.tokens_out);
    return {
      grid: { left: 40, right: 16, top: 28, bottom: 28 },
      tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        data: labels,
        axisLabel: { color: "#64748b", fontSize: 11 },
        axisLine: { lineStyle: { color: "#e2e8f0" } },
      },
      yAxis: {
        type: "value",
        minInterval: trendMode === "calls" ? 1 : undefined,
        axisLabel: { color: "#64748b", fontSize: 11 },
        splitLine: { lineStyle: { color: "#f1f5f9" } },
      },
      series: [
        {
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 6,
          data: values,
          areaStyle: { color: "rgba(244, 63, 94, 0.12)" },
          lineStyle: { color: "#e11d48", width: 2 },
          itemStyle: { color: "#e11d48" },
        },
      ],
    };
  }, [data?.by_day, trendMode]);

  const maxSkillCalls = Math.max(1, ...(data?.by_skill || []).map((s) => s.calls));

  return (
    <div className="flex h-full min-h-0 flex-col overflow-auto">
      <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 bg-white/95 px-5 py-4 backdrop-blur">
        <div>
          <h2 className="text-base font-semibold text-slate-900">AI 用量</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            日配额与近 {days} 日调用明细（深度审校约 4 次 · 快速润色约 2 次）
          </p>
        </div>
        <div className="flex gap-1 rounded-lg border border-slate-200 bg-slate-50 p-0.5">
          {([1, 7, 30] as const).map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDays(d)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                days === d
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-500 hover:text-slate-800"
              }`}
            >
              {d === 1 ? "今日" : `近${d}日`}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-4 p-5">
        {err && (
          <p className="rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-600">
            {err}
          </p>
        )}

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-medium text-rose-600">今日配额</p>
              <p className="mt-1 text-3xl font-semibold tabular-nums text-slate-900">
                {data ? (
                  <>
                    {data.used_today}
                    <span className="text-lg font-medium text-slate-400">
                      {" "}
                      / {data.quota_daily}
                    </span>
                  </>
                ) : (
                  "—"
                )}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                剩余 {data?.remaining ?? "—"}
                {data?.day ? ` · ${data.day}` : ""}
              </p>
            </div>
            <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-rose-50 text-rose-500">
              <Activity className="h-5 w-5" />
            </span>
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100">
            <div
              className={`h-full rounded-full transition-all ${
                barWarn
                  ? "bg-gradient-to-r from-amber-500 to-red-500"
                  : "bg-gradient-to-r from-red-500 to-orange-400"
              }`}
              style={{ width: `${usedPct}%` }}
            />
          </div>
        </section>

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[
            { label: "调用次数", value: loading ? "…" : String(totals.calls) },
            { label: "Run 数", value: loading ? "…" : String(totals.runs) },
            {
              label: "Token 总量",
              value: loading ? "…" : fmtTokens(tokenSum),
            },
            {
              label: "日均调用",
              value: loading ? "…" : String(avgPerDay),
            },
          ].map((c) => (
            <div
              key={c.label}
              className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
            >
              <p className="text-xs text-slate-500">{c.label}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">
                {c.value}
              </p>
            </div>
          ))}
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-slate-900">调用趋势</h3>
            <div className="flex gap-1 rounded-lg border border-slate-200 bg-slate-50 p-0.5">
              <button
                type="button"
                onClick={() => setTrendMode("calls")}
                className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                  trendMode === "calls"
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-500"
                }`}
              >
                调用次数
              </button>
              <button
                type="button"
                onClick={() => setTrendMode("tokens")}
                className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                  trendMode === "tokens"
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-500"
                }`}
              >
                Token
              </button>
            </div>
          </div>
          {loading ? (
            <p className="py-16 text-center text-sm text-slate-400">加载中…</p>
          ) : (
            <ReactECharts
              option={chartOpt}
              style={{ height: 260 }}
              notMerge
              opts={{ renderer: "canvas" }}
            />
          )}
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
          <h3 className="text-sm font-semibold text-slate-900">按能力拆分</h3>
          <p className="mt-0.5 text-xs text-slate-500">近 {days} 日 skill 调用排行</p>
          {!loading && !(data?.by_skill || []).length ? (
            <p className="py-10 text-center text-sm text-slate-400">暂无调用记录</p>
          ) : (
            <ul className="mt-4 space-y-3">
              {(data?.by_skill || []).map((s) => {
                const tok = s.tokens_in + s.tokens_out;
                const pct = Math.round((s.calls / maxSkillCalls) * 100);
                return (
                  <li key={s.skill}>
                    <div className="flex items-center justify-between gap-3 text-sm">
                      <span className="font-medium text-slate-800">
                        {skillLabel(s.skill)}
                      </span>
                      <span className="shrink-0 tabular-nums text-xs text-slate-500">
                        {s.calls} 次 · {fmtTokens(tok)} tok
                      </span>
                    </div>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="h-full rounded-full bg-rose-500/80"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
