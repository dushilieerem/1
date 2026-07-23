import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Eye, FlaskConical, LineChart, MessageCircle, Pencil, Star, Trash2 } from "lucide-react";
import { getStoredUser } from "@/lib/auth";
import {
  addFavorite,
  createComment,
  deleteCommunityPost,
  formatPostTime,
  getCommunityPost,
  listComments,
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
    void Promise.all([
      getCommunityPost(postId, { bump: takeViewBump(postId) }),
      listComments(postId),
    ])
      .then(([postData, commentData]) => {
        if (cancelled) return;
        setPost(postData.post);
        setComments(commentData.items);
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
  }, [postId]);

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
    if (!window.confirm("确认删除该帖子？")) {
      return;
    }
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

  return (
    <CommunityPageShell>
      <div className="mx-auto max-w-[1120px] space-y-5 px-5 py-6 animate-fade-up">
        <CommunityBackLink />

        <CommunityPanel>
          <header className="border-b border-slate-100 px-6 py-6 sm:px-8">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <SectionPill section={post.section} label={post.section_label} />
              <div className="flex flex-wrap items-center gap-2">
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
                    <button
                      type="button"
                      disabled={deleteBusy}
                      onClick={() => void onDelete()}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-sm font-medium text-red-600 transition hover:bg-red-50 disabled:opacity-60"
                    >
                      <Trash2 className="h-4 w-4" />
                      {deleteBusy ? "删除中…" : "删除"}
                    </button>
                    <span className="inline-flex items-center gap-1.5 rounded-lg border border-slate-100 bg-slate-50 px-3 py-1.5 text-sm text-slate-400">
                      <Star className="h-4 w-4" />
                      收藏 {post.favorite_count ?? 0}
                    </span>
                  </>
                ) : (
                  <button
                    type="button"
                    disabled={favBusy}
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
