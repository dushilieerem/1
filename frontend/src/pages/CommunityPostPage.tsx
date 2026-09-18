import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Eye, EyeOff, Flag, FlaskConical, LineChart, MessageCircle, Pencil, Pin, ScrollText, Sparkles, Star, ThumbsDown, ThumbsUp, Trash2, X } from "lucide-react";
import { getStoredUser } from "@/lib/auth";
import { runAgent, type AgentFlag } from "@/lib/agentApi";
import { useConfirm } from "@/components/ConfirmDialog";
import {
  addFavorite,
  createComment,
  createCommunityReport,
  deleteCommunityPost,
  formatPostTime,
  getCommunityPost,
  listComments,
  moderateCommunityPost,
  removeFavorite,
  takeViewBump,
  votePost,
  type CommunityComment,
  type CommunityPost,
  type ReportTargetType,
} from "@/lib/communityApi";
import { pushBrowseHistory } from "@/lib/browseHistory";
import {
  createDetectProjectFromLibraryFactors,
  openDetectPlaceholderTab,
  navigateDetectTab,
} from "@/lib/detectStore";
import {
  createStrategyProjectFromCode,
  openStrategyInNewTab,
} from "@/lib/strategyStore";
import { planCommunityDetectClone } from "@/lib/communityClone";
import {
  CommunityBackLink,
  CommunityPageShell,
  CommunityPanel,
  SectionPill,
} from "@/components/community/communityUi";
import { AuthorAvatarWithCard } from "@/components/community/AuthorProfileCard";
import {
  HighlightedCodeBlock,
  MarkdownBody,
} from "@/components/community/MarkdownBody";
import { CommentThread } from "@/components/community/CommentThread";
import { ReportDialog } from "@/components/community/ReportDialog";

function normalizeSummaryMd(raw: string): string {
  let s = (raw || "").trim();
  if (!s) return s;
  if (s.includes("\\n") && !s.includes("\n")) {
    s = s.replace(/\\n/g, "\n");
  }
  s = s.replace(/^```(?:markdown|md)?\s*/i, "").replace(/\s*```$/i, "");
  const titles = ["背景", "方法或观点", "方法", "观点", "结论", "局限"];
  for (const t of titles) {
    s = s.replace(
      new RegExp(`^(?:#{1,6}\\s*)?(?:\\*\\*)?${t}(?:\\*\\*)?\\s*[:：]?\\s*$`, "gm"),
      `## ${t}`,
    );
  }
  return s.trim();
}

type StoredPostTldr = {
  summary: string;
  flags: AgentFlag[];
  updatedAt: string;
};

function postTldrStorageKey(userId: number, postId: number) {
  return `svquant.community.tldr.u${userId}.p${postId}`;
}

function loadPostTldr(userId: number, postId: number): StoredPostTldr | null {
  try {
    const raw = localStorage.getItem(postTldrStorageKey(userId, postId));
    if (!raw) return null;
    const data = JSON.parse(raw) as StoredPostTldr;
    if (!data?.summary?.trim()) return null;
    return data;
  } catch {
    return null;
  }
}

function savePostTldr(
  userId: number,
  postId: number,
  summary: string,
  flags: AgentFlag[],
) {
  const payload: StoredPostTldr = {
    summary,
    flags,
    updatedAt: new Date().toISOString(),
  };
  localStorage.setItem(postTldrStorageKey(userId, postId), JSON.stringify(payload));
}

export function CommunityPostPage() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const user = getStoredUser();
  const confirm = useConfirm();
  const [post, setPost] = useState<CommunityPost | null>(null);
  const [comments, setComments] = useState<CommunityComment[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [cloneBusy, setCloneBusy] = useState(false);
  const [cloneErr, setCloneErr] = useState<string | null>(null);
  const [favBusy, setFavBusy] = useState(false);
  const [favErr, setFavErr] = useState<string | null>(null);
  const [voteBusy, setVoteBusy] = useState(false);
  const [highlightId, setHighlightId] = useState<number | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [modBusy, setModBusy] = useState(false);
  const [reportTarget, setReportTarget] = useState<{
    type: ReportTargetType;
    commentId?: number;
  } | null>(null);
  const [tldrBusy, setTldrBusy] = useState(false);
  const [tldrErr, setTldrErr] = useState<string | null>(null);
  const [tldrSummary, setTldrSummary] = useState<string | null>(null);
  const [tldrFlags, setTldrFlags] = useState<AgentFlag[]>([]);
  const [tldrModalOpen, setTldrModalOpen] = useState(false);

  const postId = Number(id);
  const focusComment = Number(searchParams.get("comment") || 0);

  useEffect(() => {
    if (!tldrModalOpen) return;
    const scrollY = window.scrollY;
    const { body, documentElement: html } = document;
    const prev = {
      bodyOverflow: body.style.overflow,
      htmlOverflow: html.style.overflow,
      bodyPosition: body.style.position,
      bodyTop: body.style.top,
      bodyWidth: body.style.width,
    };
    body.style.overflow = "hidden";
    html.style.overflow = "hidden";
    body.style.position = "fixed";
    body.style.top = `-${scrollY}px`;
    body.style.width = "100%";
    return () => {
      body.style.overflow = prev.bodyOverflow;
      html.style.overflow = prev.htmlOverflow;
      body.style.position = prev.bodyPosition;
      body.style.top = prev.bodyTop;
      body.style.width = prev.bodyWidth;
      window.scrollTo(0, scrollY);
    };
  }, [tldrModalOpen]);

  const reloadComments = async (pid: number) => {
    const data = await listComments(pid);
    setComments(data.items);
  };

  useEffect(() => {
    if (!Number.isFinite(postId) || postId <= 0) {
      setErr("无效的帖子 ID");
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setErr(null);
    setFavErr(null);
    void getCommunityPost(postId, { bump: takeViewBump(postId) })
      .then(async (postData) => {
        if (cancelled) return;
        if (postData.post.status === "draft") {
          navigate(`/community/post/${postId}/edit`, { replace: true });
          return;
        }
        setPost(postData.post);
        pushBrowseHistory({
          kind: "community",
          id: postData.post.id,
          title: postData.post.title || "（无标题）",
          href: `/community/post/${postData.post.id}`,
          subtitle:
            postData.post.author.display_name || postData.post.author.username,
        });
        try {
          const commentData = await listComments(postId);
          if (!cancelled) setComments(commentData.items);
        } catch {
          if (!cancelled) setComments([]);
        }
      })
      .catch((ex) => {
        if (!cancelled) {
          setErr(ex instanceof Error ? ex.message : String(ex));
          setPost(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [postId, navigate]);

  useEffect(() => {
    if (!focusComment || loading || comments.length === 0) return;
    setHighlightId(focusComment);
    const t = window.setTimeout(() => {
      const el = document.getElementById(`comment-${focusComment}`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 80);
    const clear = window.setTimeout(() => setHighlightId(null), 3500);
    return () => {
      window.clearTimeout(t);
      window.clearTimeout(clear);
    };
  }, [focusComment, loading, comments.length]);

  // 按用户+帖子恢复本地摘要（不同用户互不影响）
  useEffect(() => {
    if (!user?.id || !Number.isFinite(postId) || postId <= 0) {
      setTldrSummary(null);
      setTldrFlags([]);
      return;
    }
    const cached = loadPostTldr(Number(user.id), postId);
    if (cached) {
      setTldrSummary(cached.summary);
      setTldrFlags(cached.flags || []);
    } else {
      setTldrSummary(null);
      setTldrFlags([]);
    }
  }, [user?.id, postId]);

  const openTldrModal = () => {
    if (!user) {
      navigate(`/login?next=${encodeURIComponent(`/community/post/${postId}`)}`);
      return;
    }
    if (!tldrSummary?.trim()) {
      setTldrErr("暂无摘要，请先点击「生成摘要」");
      return;
    }
    setTldrErr(null);
    setTldrModalOpen(true);
  };

  const onGenerateTldr = async () => {
    if (!post) return;
    if (!user) {
      navigate(`/login?next=${encodeURIComponent(`/community/post/${post.id}`)}`);
      return;
    }
    setTldrErr(null);
    setTldrBusy(true);
    try {
      const res = await runAgent({
        mode: "multi",
        crew: "community_read",
        goal: "为社区帖生成 TL;DR 摘要",
        context: {
          post_id: post.id,
          title: post.title || "",
          body: post.body || "",
          code_snippet: post.code_snippet || "",
          with_risks: true,
          ...(post.platform_ref ? { platform_ref: post.platform_ref } : {}),
        },
      });
      if (!res.ok) {
        throw new Error(res.error || "生成摘要失败");
      }
      const md =
        res.outputs?.summary_md ||
        res.board?.summary_md ||
        "";
      if (!md.trim()) {
        throw new Error("摘要为空，请重试");
      }
      const summary = normalizeSummaryMd(md);
      const flags = (res.outputs?.flags || res.board?.flags || []) as AgentFlag[];
      setTldrSummary(summary);
      setTldrFlags(flags);
      savePostTldr(Number(user.id), post.id, summary, flags);
      setTldrModalOpen(true);
    } catch (ex) {
      setTldrErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setTldrBusy(false);
    }
  };

  const onToggleFavorite = async () => {
    if (!post) return;
    if (!user) {
      navigate(`/login?next=${encodeURIComponent(`/community/post/${post.id}`)}`);
      return;
    }
    if (post.author?.id != null && post.author.id === user.id) {
      setFavErr("不能收藏自己的帖子");
      return;
    }
    setFavErr(null);
    setFavBusy(true);
    try {
      const res = post.favorited
        ? await removeFavorite(post.id)
        : await addFavorite(post.id);
      setPost({
        ...post,
        favorited: res.favorited,
        favorite_count: res.favorite_count,
      });
    } catch (ex) {
      setFavErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setFavBusy(false);
    }
  };

  const onCastVote = async (next: 1 | -1) => {
    if (!post || voteBusy || post.status === "hidden") return;
    if (!user) {
      navigate(`/login?next=${encodeURIComponent(`/community/post/${post.id}`)}`);
      return;
    }
    // 自己的帖不可赞踩：静默忽略，不弹错
    if (post.author?.id != null && post.author.id === user.id) return;
    const my = post.my_vote ?? 0;
    const value = (my === next ? 0 : next) as 1 | -1 | 0;
    setVoteBusy(true);
    setFavErr(null);
    try {
      const res = await votePost(post.id, value);
      setPost({
        ...post,
        like_count: res.like_count,
        dislike_count: res.dislike_count,
        my_vote: res.my_vote,
      });
    } catch (ex) {
      setFavErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setVoteBusy(false);
    }
  };

  const onCloneToDetect = async () => {
    if (!post) return;
    if (!user) {
      navigate(`/login?next=${encodeURIComponent(`/community/post/${post.id}`)}`);
      return;
    }
    setCloneErr(null);
    const code = (post.code_snippet || "").trim();
    if (!code) {
      setCloneErr("该帖没有代码片段，无法克隆到因子检测");
      return;
    }
    setCloneBusy(true);
    const tab = openDetectPlaceholderTab();
    try {
      const plan = await planCommunityDetectClone(code);
      const displayName =
        (post.title || "").trim().slice(0, 80) ||
        (plan.kind === "library" || plan.kind === "mixed"
          ? plan.factorIds.join("+")
          : plan.suggestedName) ||
        "社区克隆";
      if (plan.kind === "library" || plan.kind === "mixed") {
        const p = await createDetectProjectFromLibraryFactors({
          title: displayName,
          factorIds: plan.factorIds,
          comboFn: plan.comboFn,
          weightMode: plan.weightMode,
          draftFactors:
            plan.kind === "mixed" ? plan.customDrafts : undefined,
        });
        navigateDetectTab(tab, p.id, p);
        return;
      }
      // 纯自定义：临时因子直开检测，跳过「新建因子」表单
      const drafts = plan.customDrafts?.length
        ? plan.customDrafts
        : [
            {
              name: plan.suggestedName || "cloned_factor",
              description: plan.suggestedName || "社区克隆",
              category: "其他",
              body: plan.code,
            },
          ];
      const p = await createDetectProjectFromLibraryFactors({
        title: displayName,
        factorIds: [],
        comboFn: plan.comboFn,
        weightMode: plan.weightMode || "sum",
        draftFactors: drafts,
      });
      navigateDetectTab(tab, p.id, p);
    } catch (ex) {
      try {
        tab?.close();
      } catch {
        /* ignore */
      }
      setCloneErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setCloneBusy(false);
    }
  };

  const onCloneToStrategy = async () => {
    if (!post) return;
    if (!user) {
      navigate(`/login?next=${encodeURIComponent(`/community/post/${post.id}`)}`);
      return;
    }
    setCloneErr(null);
    setCloneBusy(true);
    try {
      const code = (post.code_snippet || "").trim();
      if (!code) throw new Error("该帖没有代码片段，无法克隆到策略研究");
      const project = await createStrategyProjectFromCode({
        name: post.title.slice(0, 80) || `社区策略 ${post.id}`,
        description: post.title,
        strategyCode: code,
      });
      openStrategyInNewTab(project.id);
    } catch (ex) {
      setCloneErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setCloneBusy(false);
    }
  };

  const onDelete = async () => {
    if (!post) return;
    const ok = await confirm({
      title: "删除帖子",
      message: "确认删除该帖子？",
      confirmLabel: "删除",
      danger: true,
    });
    if (!ok) return;
    setDeleteBusy(true);
    setFavErr(null);
    try {
      await deleteCommunityPost(post.id);
      navigate("/community", { replace: true });
    } catch (ex) {
      setFavErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setDeleteBusy(false);
    }
  };

  const onModerate = async (payload: {
    pinned?: boolean;
    status?: "published" | "hidden";
  }) => {
    if (!post) return;
    if (payload.status === "hidden") {
      const ok = await confirm({
        title: "下架帖子",
        message: "确认下架该帖？Feed 将不再展示（管理员仍可打开并恢复）。",
        confirmLabel: "下架",
        danger: true,
      });
      if (!ok) return;
    }
    if (payload.status === "published") {
      const ok = await confirm({
        title: "恢复显示",
        message: `确认恢复「${post.title}」？恢复后将重新出现在社区 Feed。`,
        confirmLabel: "恢复",
      });
      if (!ok) return;
    }
    setModBusy(true);
    setFavErr(null);
    try {
      const data = await moderateCommunityPost(post.id, payload);
      setPost(data.post);
    } catch (ex) {
      setFavErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setModBusy(false);
    }
  };

  if (loading) {
    return (
      <CommunityPageShell>
        <div className="px-5 py-16 text-center text-sm text-slate-500">加载中…</div>
      </CommunityPageShell>
    );
  }

  if (err || !post) {
    return (
      <CommunityPageShell>
        <div className="mx-auto max-w-[1120px] px-5 py-10">
          <CommunityBackLink />
          <p className="mt-4 rounded-xl border border-red-100 bg-white px-4 py-3 text-sm text-red-600">
            {err || "帖子不存在"}
          </p>
        </div>
      </CommunityPageShell>
    );
  }

  const authorName =
    post.author.display_name || post.author.username || "匿名";
  const favorited = !!post.favorited;
  const myVote = post.my_vote ?? 0;
  const isOwnPost = !!(user && post.author?.id != null && post.author.id === user.id);
  const isAdmin = user?.role === "admin";
  const isHidden = post.status === "hidden";

  return (
    <CommunityPageShell>
      {/* 帖子主栏加宽居中；摘要入口放评论区右上角 */}
      <div className="mx-auto max-w-[1100px] px-3 py-4 animate-fade-up lg:px-5 lg:py-6">
        <div className="space-y-4 lg:space-y-5">
            <CommunityBackLink />

            {isHidden && isAdmin ? (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900 lg:px-4">
                <span>该帖已下架，游客与普通用户不可见。</span>
                <button
                  type="button"
                  disabled={modBusy}
                  onClick={() => void onModerate({ status: "published" })}
                  className="shrink-0 rounded-lg bg-amber-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-amber-500 disabled:opacity-60"
                >
                  恢复显示
                </button>
              </div>
            ) : null}

            <CommunityPanel>
          <header className="border-b border-slate-100 px-3 py-4 lg:px-8 lg:py-6">
            <div className="flex items-start justify-between gap-2">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <SectionPill section={post.section} label={post.section_label} />
                {post.is_pinned ? (
                  <span className="rounded-md bg-sky-500 px-1.5 py-0.5 text-[11px] font-semibold text-white">
                    置顶
                  </span>
                ) : null}
              </div>
              {/* 手机：摘要固定右上，避免操作栏横滑才看得见 */}
              <button
                type="button"
                className="inline-flex h-8 shrink-0 items-center gap-1 rounded-lg border border-sky-200/80 bg-white px-2.5 text-xs font-semibold text-sky-800 shadow-sm transition hover:bg-sky-50 disabled:opacity-60 lg:hidden"
                disabled={isHidden || tldrBusy}
                onClick={() => {
                  if (tldrSummary?.trim()) {
                    openTldrModal();
                    return;
                  }
                  void onGenerateTldr();
                }}
              >
                {tldrSummary?.trim() ? (
                  <>
                    <ScrollText className="h-3.5 w-3.5" />
                    摘要
                  </>
                ) : (
                  <>
                    <Sparkles className="h-3.5 w-3.5" />
                    {tldrBusy ? "…" : "生成摘要"}
                  </>
                )}
              </button>
            </div>

            <h1 className="mt-2.5 text-xl font-bold leading-snug tracking-tight text-slate-900 lg:mt-4 lg:text-3xl">
              {post.title}
            </h1>

            <div className="mt-2.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-slate-500 lg:mt-3 lg:gap-x-3 lg:gap-y-1.5 lg:text-sm">
              <span className="inline-flex items-center gap-2 font-medium text-slate-700">
                <AuthorAvatarWithCard
                  username={post.author.username}
                  name={authorName}
                  src={post.author.avatar_url}
                  size="md"
                />
                {authorName}
              </span>
              <span className="tabular-nums">{formatPostTime(post.created_at)}</span>
              <span className="inline-flex items-center gap-1">
                <Eye className="h-3.5 w-3.5" />
                {post.view_count}
              </span>
              <span className="inline-flex items-center gap-1">
                <MessageCircle className="h-3.5 w-3.5" />
                {post.comment_count ?? comments.length}
              </span>
            </div>

            {/* 手机：紧凑不换行；PC：疏朗可换行（两套布局，逻辑共用） */}
            <div className="mt-4 lg:hidden">
              <div className="flex flex-nowrap items-center gap-1.5 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                {isOwnPost ? (
                  <>
                    <span className="inline-flex h-8 min-w-[2.75rem] shrink-0 items-center justify-center gap-1 rounded-lg border border-slate-100 bg-slate-50 px-2 text-xs text-slate-400">
                      <ThumbsUp className="h-3.5 w-3.5" />
                      {post.like_count ?? 0}
                    </span>
                    <span className="inline-flex h-8 min-w-[2.75rem] shrink-0 items-center justify-center gap-1 rounded-lg border border-slate-100 bg-slate-50 px-2 text-xs text-slate-400">
                      <ThumbsDown className="h-3.5 w-3.5" />
                      {post.dislike_count ?? 0}
                    </span>
                    <span className="inline-flex h-8 min-w-[2.75rem] shrink-0 items-center justify-center gap-1 rounded-lg border border-slate-100 bg-slate-50 px-2 text-xs text-slate-400">
                      <Star className="h-3.5 w-3.5" />
                      {post.favorite_count ?? 0}
                    </span>
                    <button
                      type="button"
                      onClick={() => navigate(`/community/post/${post.id}/edit`)}
                      className="inline-flex h-8 shrink-0 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                      编辑
                    </button>
                    {!isHidden ? (
                      <button
                        type="button"
                        disabled={deleteBusy}
                        onClick={() => void onDelete()}
                        className="inline-flex h-8 shrink-0 items-center gap-1 rounded-lg border border-red-200 bg-white px-2.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-60"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        {deleteBusy ? "…" : "删除"}
                      </button>
                    ) : null}
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      disabled={voteBusy || isHidden}
                      onClick={() => void onCastVote(1)}
                      aria-label="赞"
                      className={`inline-flex h-8 min-w-[2.75rem] shrink-0 items-center justify-center gap-1 rounded-lg border px-2 text-xs font-medium tabular-nums transition disabled:opacity-60 ${
                        myVote === 1
                          ? "border-red-200 bg-red-50 text-red-700"
                          : "border-slate-200 bg-white text-slate-600 hover:border-red-200 hover:bg-red-50/60"
                      }`}
                    >
                      <ThumbsUp className={`h-3.5 w-3.5 ${myVote === 1 ? "fill-red-500 text-red-500" : ""}`} />
                      {post.like_count ?? 0}
                    </button>
                    <button
                      type="button"
                      disabled={voteBusy || isHidden}
                      onClick={() => void onCastVote(-1)}
                      aria-label="踩"
                      className={`inline-flex h-8 min-w-[2.75rem] shrink-0 items-center justify-center gap-1 rounded-lg border px-2 text-xs font-medium tabular-nums transition disabled:opacity-60 ${
                        myVote === -1
                          ? "border-slate-300 bg-slate-100 text-slate-800"
                          : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                      }`}
                    >
                      <ThumbsDown className={`h-3.5 w-3.5 ${myVote === -1 ? "fill-slate-600" : ""}`} />
                      {post.dislike_count ?? 0}
                    </button>
                    <button
                      type="button"
                      disabled={favBusy || isHidden}
                      onClick={() => void onToggleFavorite()}
                      aria-label={favorited ? "取消收藏" : "收藏"}
                      className={`inline-flex h-8 min-w-[2.75rem] shrink-0 items-center justify-center gap-1 rounded-lg border px-2 text-xs font-medium tabular-nums transition disabled:opacity-60 ${
                        favorited
                          ? "border-amber-200 bg-amber-50 text-amber-700"
                          : "border-slate-200 bg-white text-slate-600 hover:border-amber-200 hover:bg-amber-50/60"
                      }`}
                    >
                      <Star className={`h-3.5 w-3.5 ${favorited ? "fill-amber-500 text-amber-500" : ""}`} />
                      {post.favorite_count ?? 0}
                    </button>
                    {!isHidden ? (
                      <button
                        type="button"
                        onClick={() => {
                          if (!user) {
                            navigate(
                              `/login?next=${encodeURIComponent(`/community/post/${post.id}`)}`,
                            );
                            return;
                          }
                          setReportTarget({ type: "post" });
                        }}
                        aria-label="举报"
                        className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-amber-50/60"
                      >
                        <Flag className="h-3.5 w-3.5" />
                      </button>
                    ) : null}
                  </>
                )}
              </div>
            </div>

            <div className="mt-4 hidden flex-wrap items-center gap-2 lg:flex">
              {isOwnPost ? (
                <>
                  <span className="inline-flex items-center gap-1.5 rounded-lg border border-slate-100 bg-slate-50 px-3 py-1.5 text-sm text-slate-400">
                    <ThumbsUp className="h-4 w-4" />
                    {post.like_count ?? 0}
                  </span>
                  <span className="inline-flex items-center gap-1.5 rounded-lg border border-slate-100 bg-slate-50 px-3 py-1.5 text-sm text-slate-400">
                    <ThumbsDown className="h-4 w-4" />
                    {post.dislike_count ?? 0}
                  </span>
                  <span className="inline-flex items-center gap-1.5 rounded-lg border border-slate-100 bg-slate-50 px-3 py-1.5 text-sm text-slate-400">
                    <Star className="h-4 w-4" />
                    {post.favorite_count ?? 0}
                  </span>
                  <button
                    type="button"
                    onClick={() => navigate(`/community/post/${post.id}/edit`)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                  >
                    <Pencil className="h-4 w-4" />
                    编辑
                  </button>
                  {!isHidden ? (
                    <button
                      type="button"
                      disabled={deleteBusy}
                      onClick={() => void onDelete()}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-60"
                    >
                      <Trash2 className="h-4 w-4" />
                      {deleteBusy ? "删除中…" : "删除"}
                    </button>
                  ) : null}
                </>
              ) : (
                <>
                  <button
                    type="button"
                    disabled={voteBusy || isHidden}
                    onClick={() => void onCastVote(1)}
                    className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium tabular-nums transition disabled:opacity-60 ${
                      myVote === 1
                        ? "border-red-200 bg-red-50 text-red-700"
                        : "border-slate-200 bg-white text-slate-600 hover:border-red-200 hover:bg-red-50/60"
                    }`}
                  >
                    <ThumbsUp className={`h-4 w-4 ${myVote === 1 ? "fill-red-500 text-red-500" : ""}`} />
                    {post.like_count ?? 0}
                  </button>
                  <button
                    type="button"
                    disabled={voteBusy || isHidden}
                    onClick={() => void onCastVote(-1)}
                    className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium tabular-nums transition disabled:opacity-60 ${
                      myVote === -1
                        ? "border-slate-300 bg-slate-100 text-slate-800"
                        : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    <ThumbsDown className={`h-4 w-4 ${myVote === -1 ? "fill-slate-600" : ""}`} />
                    {post.dislike_count ?? 0}
                  </button>
                  <button
                    type="button"
                    disabled={favBusy || isHidden}
                    onClick={() => void onToggleFavorite()}
                    className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium tabular-nums transition disabled:opacity-60 ${
                      favorited
                        ? "border-amber-200 bg-amber-50 text-amber-700"
                        : "border-slate-200 bg-white text-slate-600 hover:border-amber-200 hover:bg-amber-50/60"
                    }`}
                  >
                    <Star className={`h-4 w-4 ${favorited ? "fill-amber-500 text-amber-500" : ""}`} />
                    {post.favorite_count ?? 0}
                  </button>
                  {!isHidden ? (
                    <button
                      type="button"
                      onClick={() => {
                        if (!user) {
                          navigate(
                            `/login?next=${encodeURIComponent(`/community/post/${post.id}`)}`,
                          );
                          return;
                        }
                        setReportTarget({ type: "post" });
                      }}
                      aria-label="举报"
                      className="inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-slate-600 hover:bg-amber-50/60"
                    >
                      <Flag className="h-4 w-4" />
                    </button>
                  ) : null}
                </>
              )}

              <button
                type="button"
                className="inline-flex items-center gap-1.5 rounded-lg border border-sky-200/80 bg-white px-3 py-1.5 text-sm font-semibold text-sky-800 shadow-sm transition hover:bg-sky-50 disabled:opacity-60"
                disabled={isHidden || tldrBusy}
                onClick={() => {
                  if (tldrSummary?.trim()) {
                    openTldrModal();
                    return;
                  }
                  void onGenerateTldr();
                }}
              >
                {tldrSummary?.trim() ? (
                  <>
                    <ScrollText className="h-4 w-4" />
                    显示摘要
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4" />
                    {tldrBusy ? "生成中…" : "生成摘要"}
                  </>
                )}
              </button>
            </div>

            {isAdmin ? (
              <div className="mt-2 flex flex-wrap items-center gap-1.5 sm:gap-2">
                <button
                  type="button"
                  disabled={modBusy}
                  onClick={() => void onModerate({ pinned: !post.is_pinned })}
                  className="inline-flex items-center gap-1 rounded-lg border border-sky-200 bg-sky-50 px-2.5 py-1.5 text-xs font-medium text-sky-800 hover:bg-sky-100 disabled:opacity-60 sm:gap-1.5 sm:px-3 sm:text-sm"
                >
                  <Pin className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                  {post.is_pinned ? "取消置顶" : "置顶"}
                </button>
                {isHidden ? (
                  <button
                    type="button"
                    disabled={modBusy}
                    onClick={() => void onModerate({ status: "published" })}
                    className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100 disabled:opacity-60 sm:gap-1.5 sm:px-3 sm:text-sm"
                  >
                    <Eye className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                    恢复
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={modBusy}
                    onClick={() => void onModerate({ status: "hidden" })}
                    className="inline-flex items-center gap-1 rounded-lg border border-amber-200 bg-white px-2.5 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-50 disabled:opacity-60 sm:gap-1.5 sm:px-3 sm:text-sm"
                  >
                    <EyeOff className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                    下架
                  </button>
                )}
                {!isOwnPost ? (
                  <button
                    type="button"
                    onClick={() => navigate(`/community/post/${post.id}/edit`)}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 sm:gap-1.5 sm:px-3 sm:text-sm"
                  >
                    <Pencil className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                    编辑
                  </button>
                ) : null}
              </div>
            ) : null}

            {tldrErr ? <p className="mt-2 text-sm text-red-600">{tldrErr}</p> : null}
            {favErr ? <p className="mt-2 text-sm text-red-600">{favErr}</p> : null}
          </header>

          <div className="px-3 py-5 lg:px-8 lg:py-8">
            <MarkdownBody source={post.body || ""} />
          </div>

          {post.code_snippet ? (
            <div className="border-t border-slate-100 px-3 py-4 lg:px-8 lg:py-5">
              <div className="mb-2 flex flex-col gap-2 lg:mb-2 lg:flex-row lg:flex-wrap lg:items-center lg:justify-between">
                <h2 className="text-sm font-semibold text-slate-800">代码</h2>
                <div className="flex flex-wrap items-center gap-2">
                  {post.section === "factor" ? (
                    <button
                      type="button"
                      disabled={cloneBusy}
                      onClick={() => void onCloneToDetect()}
                      className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-red-500 px-3 py-2 text-sm font-semibold text-white shadow-sm shadow-red-200/50 transition hover:bg-red-400 active:scale-[0.98] disabled:opacity-60 sm:w-auto lg:py-1.5"
                    >
                      <FlaskConical className="h-4 w-4 shrink-0" />
                      <span className="lg:hidden">{cloneBusy ? "处理中…" : "克隆到因子"}</span>
                      <span className="hidden lg:inline">
                        {cloneBusy ? "处理中…" : "克隆到因子检测"}
                      </span>
                    </button>
                  ) : null}
                  {post.section === "strategy" ? (
                    <button
                      type="button"
                      disabled={cloneBusy}
                      onClick={() => void onCloneToStrategy()}
                      className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-amber-500 px-3 py-2 text-sm font-semibold text-white shadow-sm shadow-amber-200/50 transition hover:bg-amber-400 active:scale-[0.98] disabled:opacity-60 sm:w-auto lg:py-1.5"
                    >
                      <LineChart className="h-4 w-4 shrink-0" />
                      <span className="lg:hidden">{cloneBusy ? "处理中…" : "克隆到策略"}</span>
                      <span className="hidden lg:inline">
                        {cloneBusy ? "处理中…" : "克隆到策略研究"}
                      </span>
                    </button>
                  ) : null}
                </div>
              </div>
              {cloneErr ? (
                <p className="mb-2 break-words rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
                  {cloneErr}
                </p>
              ) : null}
              <div className="min-w-0 overflow-x-auto">
                <HighlightedCodeBlock code={post.code_snippet} />
              </div>
            </div>
          ) : (
            <div className="border-t border-slate-100 px-3 py-4 text-sm text-slate-400 lg:px-8">
              {post.section === "strategy"
                ? "本帖无代码片段，无法克隆到策略研究。"
                : post.section === "factor"
                  ? "本帖无代码片段，无法克隆到因子检测。"
                  : "本帖无代码片段。"}
            </div>
          )}
        </CommunityPanel>

        <CommunityPanel>
          <div className="border-b border-slate-100 px-3 py-3 lg:px-5 lg:py-3.5">
            <h2 className="text-sm font-bold text-slate-900">
              评论 {comments.length > 0 ? `· ${comments.length}` : ""}
            </h2>
          </div>
          <CommentThread
            comments={comments}
            postAuthorId={post.author.id}
            highlightId={highlightId}
            canInteract={!!user}
            currentUserId={user?.id}
            onNeedLogin={() =>
              navigate(
                `/login?next=${encodeURIComponent(`/community/post/${post.id}`)}`,
              )
            }
            onCommentsChange={setComments}
            onSubmitComment={async ({ body, parentId, images }) => {
              await createComment(post.id, body, {
                parentId,
                images,
              });
              await reloadComments(post.id);
              setPost({
                ...post,
                comment_count: (post.comment_count || 0) + 1,
              });
            }}
            onReportComment={(c) => {
              setReportTarget({ type: "comment", commentId: c.id });
            }}
          />
        </CommunityPanel>
        </div>
      </div>

      {tldrModalOpen && tldrSummary ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4">
          <div
            className="absolute inset-0"
            onClick={() => setTldrModalOpen(false)}
            aria-hidden
          />
          <div
            className="relative z-10 flex max-h-[min(88dvh,640px)] w-full max-w-lg flex-col overflow-hidden rounded-t-2xl border border-slate-200 bg-white shadow-2xl sm:rounded-2xl"
            onWheel={(e) => e.stopPropagation()}
            onTouchMove={(e) => e.stopPropagation()}
          >
            <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-5 py-3.5">
              <h2 className="text-base font-semibold text-slate-900">AI 摘要</h2>
              <button
                type="button"
                onClick={() => setTldrModalOpen(false)}
                className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
                aria-label="关闭"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4">
              <MarkdownBody
                source={tldrSummary}
                forceMarkdown
                className="text-[14px] leading-6 [&_h2]:mb-1.5 [&_h2]:mt-3 [&_h2]:text-[15px] [&_h2]:first:mt-0 [&_li]:leading-6 [&_p]:mb-2 [&_p]:leading-6"
              />
              {tldrFlags.length > 0 ? (
                <div className="mt-4 border-t border-slate-100 pt-3">
                  <p className="mb-1 text-[12px] font-medium text-slate-600">阅读提示</p>
                  <ul className="space-y-1 text-[12px] leading-relaxed text-slate-500">
                    {tldrFlags.map((f, i) => (
                      <li key={`${f.code || "flag"}-${i}`}>
                        · {f.message || f.code || "阅读提示"}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
            <div className="flex shrink-0 items-center justify-between gap-2 border-t border-slate-100 px-5 py-3">
              <button
                type="button"
                disabled={tldrBusy || isHidden}
                onClick={() => void onGenerateTldr()}
                className="inline-flex items-center gap-1.5 rounded-lg border border-sky-200 bg-white px-3 py-1.5 text-xs font-semibold text-sky-800 hover:bg-sky-50 disabled:opacity-60"
              >
                <Sparkles className="h-3.5 w-3.5" />
                {tldrBusy ? "生成中…" : "重新生成"}
              </button>
              <button
                type="button"
                onClick={() => setTldrModalOpen(false)}
                className="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <ReportDialog
        open={!!reportTarget}
        targetType={reportTarget?.type || "post"}
        onClose={() => setReportTarget(null)}
        onSubmit={async ({ reason, detail }) => {
          if (!reportTarget || !post) return;
          await createCommunityReport({
            target_type: reportTarget.type,
            post_id: post.id,
            comment_id:
              reportTarget.type === "comment" ? reportTarget.commentId : null,
            reason,
            detail,
          });
        }}
      />
    </CommunityPageShell>
  );
}
