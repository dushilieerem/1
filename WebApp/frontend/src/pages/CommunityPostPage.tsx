import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Eye, EyeOff, FlaskConical, LineChart, MessageCircle, Pencil, Pin, Star, Trash2 } from "lucide-react";
import { getStoredUser } from "@/lib/auth";
import { useConfirm } from "@/components/ConfirmDialog";
import {
  addFavorite,
  createComment,
  deleteCommunityPost,
  formatPostTime,
  getCommunityPost,
  listComments,
  moderateCommunityPost,
  removeFavorite,
  takeViewBump,
  type CommunityComment,
  type CommunityPost,
} from "@/lib/communityApi";
import { resolveCommunityCloneTarget } from "@/lib/communityClone";
import {
  createDetectProjectForClone,
  openDetectInNewTab,
} from "@/lib/detectStore";
import { extractDefName } from "@/lib/factorCatalog";
import {
  createStrategyProjectFromCode,
  openStrategyInNewTab,
} from "@/lib/strategyStore";
import type { CommunityCloneState } from "@/pages/FactorCustomPage";
import {
  AuthorAvatar,
  CommunityBackLink,
  CommunityPageShell,
  CommunityPanel,
  SectionPill,
} from "@/components/community/communityUi";
import {
  HighlightedCodeBlock,
  MarkdownBody,
} from "@/components/community/MarkdownBody";
import { CommentThread } from "@/components/community/CommentThread";

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
  const [highlightId, setHighlightId] = useState<number | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [modBusy, setModBusy] = useState(false);

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

  const onCloneToDetect = async () => {
    if (!post) return;
    if (!user) {
      navigate(`/login?next=${encodeURIComponent(`/community/post/${post.id}`)}`);
      return;
    }
    setCloneErr(null);
    setCloneBusy(true);
    try {
      const code = post.code_snippet || "";
      const target = await resolveCommunityCloneTarget(code);
      const fallbackName =
        target.kind === "custom"
          ? target.defName || `社区因子 ${post.id}`
          : target.factor.description || target.factor.name;
      const displayName = (post.title || "").trim().slice(0, 80) || fallbackName;

      if (target.kind === "public" || target.kind === "owned_custom") {
        // 始终新建检测项目；已入库自定义因子也直接进检测并预选
        const factorCode = target.factor.name;
        const p = await createDetectProjectForClone(factorCode, displayName);
        openDetectInNewTab(p.id);
        return;
      }
      const defName = target.defName || extractDefName(code) || `community_${post.id}`;
      const state: CommunityCloneState = {
        communityClone: true,
        postId: post.id,
        title: post.title,
        body: code.trim(),
        name: defName,
        description: post.title,
      };
      navigate("/factor/library/custom/new", { state });
    } catch (ex) {
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
  const isOwnPost = !!(user && post.author?.id != null && post.author.id === user.id);
  const isAdmin = user?.role === "admin";
  const isHidden = post.status === "hidden";

  return (
    <CommunityPageShell>
      <div className="mx-auto max-w-[1120px] space-y-5 px-5 py-6 animate-fade-up">
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
                )}
              </div>
            </div>
            <h1 className="mt-4 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
              {post.title}
            </h1>
            <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm text-slate-500">
              <span className="inline-flex items-center gap-2 font-medium text-slate-700">
                <AuthorAvatar name={authorName} size="md" />
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
                  <button
                    type="button"
                    disabled={cloneBusy}
                    onClick={() => void onCloneToDetect()}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-red-500 px-3 py-1.5 text-sm font-semibold text-white shadow-sm shadow-red-200/50 transition hover:bg-red-400 active:scale-[0.98] disabled:opacity-60"
                  >
                    <FlaskConical className="h-4 w-4" />
                    {cloneBusy ? "处理中…" : "克隆到因子检测"}
                  </button>
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
              本帖无代码片段，无法克隆到因子检测或策略研究。
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
          />
        </CommunityPanel>
      </div>
    </CommunityPageShell>
  );
}
