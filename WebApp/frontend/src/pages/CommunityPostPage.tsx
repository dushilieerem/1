import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Eye, EyeOff, Flag, FlaskConical, LineChart, MessageCircle, Pencil, Pin, Sparkles, Star, ThumbsDown, ThumbsUp, Trash2, X } from "lucide-react";
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
  createDetectProjectFromSnippet,
  openDetectInNewTab,
} from "@/lib/detectStore";
import {
  builtinCategoryLabelsFromFactors,
  loadFactors,
} from "@/lib/factorCatalog";
import { listAllUserLibraryFactors } from "@/lib/userFactorLibraries";
import {
  createStrategyProjectFromCode,
  openStrategyInNewTab,
} from "@/lib/strategyStore";
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
  const [cloneModalOpen, setCloneModalOpen] = useState(false);
  const [cloneName, setCloneName] = useState("");
  const [cloneDesc, setCloneDesc] = useState("");
  const [cloneCategory, setCloneCategory] = useState("其他");
  const [cloneFormErr, setCloneFormErr] = useState<string | null>(null);
  const [categoryOptions, setCategoryOptions] = useState<string[]>(["其他"]);
  const [takenFactorNames, setTakenFactorNames] = useState<Set<string>>(
    () => new Set(),
  );
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

  const postId = Number(id);
  const focusComment = Number(searchParams.get("comment") || 0);

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
          subtitle: postData.post.author_name || postData.post.author_username,
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
      setTldrSummary(normalizeSummaryMd(md));
      setTldrFlags(
        (res.outputs?.flags || res.board?.flags || []) as AgentFlag[],
      );
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
    setCloneFormErr(null);
    const code = (post.code_snippet || "").trim();
    if (!code) {
      setCloneErr("该帖没有代码片段，无法克隆到因子检测");
      return;
    }
    setCloneName("");
    setCloneDesc("");
    setCloneCategory("");
    setCloneModalOpen(true);

    void Promise.all([
      loadFactors(true).catch(() => []),
      listAllUserLibraryFactors().catch(() => []),
    ]).then(([fs, userRows]) => {
      const cats = builtinCategoryLabelsFromFactors(
        fs.filter((f) => f.library !== "custom_lib"),
      );
      setCategoryOptions([...cats, "其他"]);
      const taken = new Set<string>();
      for (const f of fs) {
        if (f.library === "custom_lib") continue;
        taken.add(f.name);
        if (f.methodName) taken.add(f.methodName);
      }
      for (const r of userRows) taken.add(r.name);
      setTakenFactorNames(taken);
    });
  };

  const confirmCloneToDetect = async () => {
    if (!post) return;
    setCloneFormErr(null);
    const name = cloneName.trim();
    const description = cloneDesc.trim();
    const category = cloneCategory.trim();
    if (!name) {
      setCloneFormErr("请填写因子代码名");
      return;
    }
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) {
      setCloneFormErr("代码名须为字母开头的标识符（字母/数字/下划线）");
      return;
    }
    if (!description) {
      setCloneFormErr("请填写中文解释");
      return;
    }
    if (!category) {
      setCloneFormErr("请选择分类");
      return;
    }
    if (takenFactorNames.has(name)) {
      setCloneFormErr(
        `「${name}」与内置或已有因子库重名，请重新命名后再确定`,
      );
      return;
    }
    setCloneBusy(true);
    try {
      // 再拉一次，避免弹窗打开后别人刚入库导致漏检
      const [fs, userRows] = await Promise.all([
        loadFactors(true).catch(() => []),
        listAllUserLibraryFactors().catch(() => []),
      ]);
      const taken = new Set<string>();
      for (const f of fs) {
        if (f.library === "custom_lib") continue;
        taken.add(f.name);
        if (f.methodName) taken.add(f.methodName);
      }
      for (const r of userRows) taken.add(r.name);
      if (taken.has(name)) {
        setTakenFactorNames(taken);
        setCloneFormErr(
          `「${name}」与内置或已有因子库重名，请重新命名后再确定`,
        );
        return;
      }

      const code = post.code_snippet || "";
      const displayName =
        (post.title || "").trim().slice(0, 80) || description || name;
      const p = await createDetectProjectFromSnippet({
        title: displayName,
        code,
        name,
        description,
        category,
      });
      setCloneModalOpen(false);
      openDetectInNewTab(p.id);
    } catch (ex) {
      setCloneFormErr(ex instanceof Error ? ex.message : String(ex));
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
      {/* 知乎式：主栏左移、右侧栏给摘要；主栏仍 max-w 1120，卡片宽度不变 */}
      <div className="mx-auto max-w-[1440px] px-5 py-6 animate-fade-up">
        <div className="flex items-start gap-5">
          <div className="w-full min-w-0 max-w-[1120px] space-y-5">
            <CommunityBackLink />

            {isHidden && isAdmin ? (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
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
          <header className="border-b border-slate-100 px-6 py-6 sm:px-8">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <SectionPill section={post.section} label={post.section_label} />
                {post.is_pinned ? (
                  <span className="rounded-md bg-sky-500 px-1.5 py-0.5 text-[11px] font-semibold text-white">
                    置顶
                  </span>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {isAdmin ? (
                  <>
                    <button
                      type="button"
                      disabled={modBusy}
                      onClick={() =>
                        void onModerate({ pinned: !post.is_pinned })
                      }
                      className="inline-flex items-center gap-1.5 rounded-lg border border-sky-200 bg-sky-50 px-3 py-1.5 text-sm font-medium text-sky-800 transition hover:bg-sky-100 disabled:opacity-60"
                    >
                      <Pin className="h-4 w-4" />
                      {post.is_pinned ? "取消置顶" : "置顶"}
                    </button>
                    {isHidden ? (
                      <button
                        type="button"
                        disabled={modBusy}
                        onClick={() => void onModerate({ status: "published" })}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-700 transition hover:bg-emerald-100 disabled:opacity-60"
                      >
                        <Eye className="h-4 w-4" />
                        恢复显示
                      </button>
                    ) : (
                      <button
                        type="button"
                        disabled={modBusy}
                        onClick={() => void onModerate({ status: "hidden" })}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-amber-200 bg-white px-3 py-1.5 text-sm font-medium text-amber-700 transition hover:bg-amber-50 disabled:opacity-60"
                      >
                        <EyeOff className="h-4 w-4" />
                        下架
                      </button>
                    )}
                    {!isOwnPost ? (
                      <button
                        type="button"
                        onClick={() => navigate(`/community/post/${post.id}/edit`)}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                      >
                        <Pencil className="h-4 w-4" />
                        编辑
                      </button>
                    ) : null}
                  </>
                ) : null}
                {isOwnPost ? (
                  <>
                    <span className="inline-flex items-center gap-1.5 rounded-lg border border-slate-100 bg-slate-50 px-3 py-1.5 text-sm text-slate-400">
                      <ThumbsUp className="h-4 w-4" />
                      赞
                      <span className="text-xs opacity-70">{post.like_count ?? 0}</span>
                    </span>
                    <span className="inline-flex items-center gap-1.5 rounded-lg border border-slate-100 bg-slate-50 px-3 py-1.5 text-sm text-slate-400">
                      <ThumbsDown className="h-4 w-4" />
                      踩
                      <span className="text-xs opacity-70">
                        {post.dislike_count ?? 0}
                      </span>
                    </span>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      disabled={voteBusy || isHidden}
                      onClick={() => void onCastVote(1)}
                      className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition disabled:opacity-60 ${
                        myVote === 1
                          ? "border-red-200 bg-red-50 text-red-700 hover:bg-red-100"
                          : "border-slate-200 bg-white text-slate-600 hover:border-red-200 hover:bg-red-50/60 hover:text-red-700"
                      }`}
                    >
                      <ThumbsUp
                        className={`h-4 w-4 ${myVote === 1 ? "fill-red-500 text-red-500" : ""}`}
                      />
                      赞
                      <span className="text-xs opacity-70">{post.like_count ?? 0}</span>
                    </button>
                    <button
                      type="button"
                      disabled={voteBusy || isHidden}
                      onClick={() => void onCastVote(-1)}
                      className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition disabled:opacity-60 ${
                        myVote === -1
                          ? "border-slate-300 bg-slate-100 text-slate-800 hover:bg-slate-200"
                          : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-800"
                      }`}
                    >
                      <ThumbsDown
                        className={`h-4 w-4 ${myVote === -1 ? "fill-slate-600 text-slate-700" : ""}`}
                      />
                      踩
                      <span className="text-xs opacity-70">
                        {post.dislike_count ?? 0}
                      </span>
                    </button>
                  </>
                )}
                {isOwnPost ? (
                  <>
                    <button
                      type="button"
                      onClick={() => navigate(`/community/post/${post.id}/edit`)}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                    >
                      <Pencil className="h-4 w-4" />
                      编辑
                    </button>
                    {!isHidden ? (
                      <button
                        type="button"
                        disabled={deleteBusy}
                        onClick={() => void onDelete()}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-sm font-medium text-red-600 transition hover:bg-red-50 disabled:opacity-60"
                      >
                        <Trash2 className="h-4 w-4" />
                        {deleteBusy ? "删除中…" : "删除"}
                      </button>
                    ) : null}
                    <span className="inline-flex items-center gap-1.5 rounded-lg border border-slate-100 bg-slate-50 px-3 py-1.5 text-sm text-slate-400">
                      <Star className="h-4 w-4" />
                      收藏 {post.favorite_count ?? 0}
                    </span>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      disabled={favBusy || isHidden}
                      onClick={() => void onToggleFavorite()}
                      className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition disabled:opacity-60 ${
                        favorited
                          ? "border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100"
                          : "border-slate-200 bg-white text-slate-600 hover:border-amber-200 hover:bg-amber-50/60 hover:text-amber-700"
                      }`}
                    >
                      <Star
                        className={`h-4 w-4 ${favorited ? "fill-amber-500 text-amber-500" : ""}`}
                      />
                      {favorited ? "已收藏" : "收藏"}
                      <span className="text-xs opacity-70">
                        {post.favorite_count ?? 0}
                      </span>
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
                        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 transition hover:border-amber-200 hover:bg-amber-50/60 hover:text-amber-800"
                      >
                        <Flag className="h-4 w-4" />
                        举报
                      </button>
                    ) : null}
                  </>
                )}
              </div>
            </div>
            <h1 className="mt-4 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
              {post.title}
            </h1>
            <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm text-slate-500">
              <span className="inline-flex items-center gap-2 font-medium text-slate-700">
                <AuthorAvatarWithCard
                  username={post.author.username}
                  name={authorName}
                  src={post.author.avatar_url}
                  size="md"
                />
                {authorName}
              </span>
              <span>发布于 {formatPostTime(post.created_at)}</span>
              <span className="inline-flex items-center gap-1">
                <Eye className="h-3.5 w-3.5" />
                {post.view_count}
              </span>
              <span className="inline-flex items-center gap-1">
                <MessageCircle className="h-3.5 w-3.5" />
                {post.comment_count ?? comments.length}
              </span>
              <span className="inline-flex items-center gap-1">
                <ThumbsUp className="h-3.5 w-3.5" />
                {post.like_count ?? 0}
              </span>
              <span className="inline-flex items-center gap-1">
                <ThumbsDown className="h-3.5 w-3.5" />
                {post.dislike_count ?? 0}
              </span>
            </div>
            {favErr && <p className="mt-2 text-sm text-red-600">{favErr}</p>}
          </header>

          <div className="px-6 py-8 sm:px-8">
            <MarkdownBody source={post.body || ""} />
          </div>

          {post.code_snippet ? (
            <div className="border-t border-slate-100 px-6 py-5 sm:px-8">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-semibold text-slate-800">代码</h2>
                <div className="flex flex-wrap items-center gap-2">
                  {post.section !== "strategy" ? (
                    <button
                      type="button"
                      disabled={cloneBusy}
                      onClick={() => void onCloneToDetect()}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-red-500 px-3 py-1.5 text-sm font-semibold text-white shadow-sm shadow-red-200/50 transition hover:bg-red-400 active:scale-[0.98] disabled:opacity-60"
                    >
                      <FlaskConical className="h-4 w-4" />
                      {cloneBusy ? "处理中…" : "克隆到因子检测"}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    disabled={cloneBusy}
                    onClick={() => void onCloneToStrategy()}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 active:scale-[0.98] disabled:opacity-60"
                  >
                    <LineChart className="h-4 w-4" />
                    克隆到策略研究
                  </button>
                </div>
              </div>
              {cloneErr && <p className="mb-2 text-sm text-red-600">{cloneErr}</p>}
              <HighlightedCodeBlock code={post.code_snippet} />
            </div>
          ) : (
            <div className="border-t border-slate-100 px-6 py-4 text-sm text-slate-400 sm:px-8">
              {post.section === "strategy"
                ? "本帖无代码片段，无法克隆到策略研究。"
                : "本帖无代码片段，无法克隆到因子检测或策略研究。"}
            </div>
          )}
        </CommunityPanel>

        <CommunityPanel>
          <div className="border-b border-slate-100 px-5 py-3.5">
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

          <aside className="sticky top-24 hidden w-[300px] shrink-0 self-start pt-8 xl:block">
            <div className="space-y-3">
              <button
                type="button"
                disabled={tldrBusy || isHidden}
                onClick={() => void onGenerateTldr()}
                className="inline-flex items-center gap-1.5 rounded-lg border border-sky-200/80 bg-white px-3 py-1.5 text-sm font-semibold text-sky-800 shadow-sm transition hover:bg-sky-50 disabled:opacity-60"
              >
                <Sparkles className="h-4 w-4" />
                {tldrBusy ? "生成中…" : tldrSummary ? "重新生成" : "生成摘要"}
              </button>
              {tldrErr ? <p className="text-sm text-red-600">{tldrErr}</p> : null}
              {tldrSummary ? (
                <div className="max-h-[calc(100vh-8rem)] overflow-y-auto rounded-xl border border-slate-200/80 bg-white px-3.5 py-3 shadow-sm">
                  <MarkdownBody
                    source={tldrSummary}
                    forceMarkdown
                    className="text-[13px] leading-6 [&_h2]:mb-1.5 [&_h2]:mt-3 [&_h2]:text-[15px] [&_h2]:first:mt-0 [&_li]:leading-6 [&_p]:mb-2 [&_p]:leading-6"
                  />
                  {tldrFlags.length > 0 ? (
                    <div className="mt-3 border-t border-slate-100 pt-2">
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
              ) : (
                <p className="rounded-lg bg-white/70 px-3.5 py-3 text-[13px] leading-relaxed text-slate-500">
                  AI 读帖助手会提炼背景、方法与结论，并标出阅读时需注意的局限。点上方即可生成短摘要。
                </p>
              )}
            </div>
          </aside>
        </div>
      </div>

      <div className="fixed bottom-5 right-5 z-30 w-[min(20rem,calc(100vw-2rem))] space-y-2 xl:hidden">
        <button
          type="button"
          disabled={tldrBusy || isHidden}
          onClick={() => void onGenerateTldr()}
          className="inline-flex items-center gap-1.5 rounded-full border border-sky-200 bg-white px-3.5 py-2 text-sm font-semibold text-sky-800 shadow-md transition hover:bg-sky-50 disabled:opacity-60"
        >
          <Sparkles className="h-4 w-4" />
          {tldrBusy ? "生成中…" : tldrSummary ? "重新生成" : "生成摘要"}
        </button>
        {tldrErr ? (
          <p className="rounded-lg bg-white px-3 py-2 text-sm text-red-600 shadow">{tldrErr}</p>
        ) : null}
        {tldrSummary ? (
          <div className="max-h-[40vh] overflow-y-auto rounded-xl border border-slate-200 bg-white px-3.5 py-3 shadow-lg">
            <h2 className="mb-2 text-sm font-semibold text-slate-800">AI 摘要</h2>
            <MarkdownBody
              source={tldrSummary}
              forceMarkdown
              className="text-[13px] leading-6 [&_h2]:mb-1.5 [&_h2]:mt-3 [&_h2]:text-[15px] [&_h2]:first:mt-0"
            />
          </div>
        ) : null}
      </div>

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

      {cloneModalOpen ? (
        <div className="fixed inset-0 z-[130] flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-base font-bold text-slate-900">新建因子</h3>
              <button
                type="button"
                onClick={() => setCloneModalOpen(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-3 text-sm">
              <label className="block text-xs text-slate-500">
                因子代码名
                <input
                  value={cloneName}
                  onChange={(e) => {
                    setCloneName(e.target.value);
                    const n = e.target.value.trim();
                    if (n && takenFactorNames.has(n)) {
                      setCloneFormErr(
                        `「${n}」与内置或已有因子库重名，请重新命名后再确定`,
                      );
                    } else if (cloneFormErr?.includes("重名")) {
                      setCloneFormErr(null);
                    }
                  }}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm outline-none focus:border-blue-400"
                />
              </label>
              <label className="block text-xs text-slate-500">
                中文解释
                <input
                  value={cloneDesc}
                  onChange={(e) => setCloneDesc(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
                />
              </label>
              <label className="block text-xs text-slate-500">
                分类
                <select
                  value={cloneCategory}
                  onChange={(e) => setCloneCategory(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
                >
                  <option value="">请选择</option>
                  {categoryOptions.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              {cloneFormErr ? (
                <p className="text-xs text-red-600">{cloneFormErr}</p>
              ) : null}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setCloneModalOpen(false)}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                取消
              </button>
              <button
                type="button"
                disabled={cloneBusy}
                onClick={() => void confirmCloneToDetect()}
                className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60"
              >
                {cloneBusy ? "处理中…" : "确定"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </CommunityPageShell>
  );
}
