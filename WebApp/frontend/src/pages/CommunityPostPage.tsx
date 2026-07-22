import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Eye, MessageCircle, Star } from "lucide-react";
import { getStoredUser } from "@/lib/auth";
import {
  addFavorite,
  createComment,
  formatPostTime,
  getCommunityPost,
  listComments,
  removeFavorite,
  takeViewBump,
  type CommunityComment,
  type CommunityPost,
} from "@/lib/communityApi";
import {
  AuthorAvatar,
  CommunityBackLink,
  CommunityPageShell,
  CommunityPanel,
  PrimaryButton,
  SectionPill,
  fieldClassName,
} from "@/components/community/communityUi";

export function CommunityPostPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const user = getStoredUser();
  const [post, setPost] = useState<CommunityPost | null>(null);
  const [comments, setComments] = useState<CommunityComment[]>([]);
  const [commentBody, setCommentBody] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [commentErr, setCommentErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [favBusy, setFavBusy] = useState(false);

  const postId = Number(id);

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

  const onToggleFavorite = async () => {
    if (!post) return;
    if (!user) {
      navigate(`/login?next=${encodeURIComponent(`/community/post/${post.id}`)}`);
      return;
    }
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
      setCommentErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setFavBusy(false);
    }
  };

  const onSubmitComment = async (e: FormEvent) => {
    e.preventDefault();
    if (!post) return;
    if (!user) {
      navigate(`/login?next=${encodeURIComponent(`/community/post/${post.id}`)}`);
      return;
    }
    setCommentErr(null);
    setSubmitting(true);
    try {
      await createComment(post.id, commentBody);
      setCommentBody("");
      await reloadComments(post.id);
      setPost({
        ...post,
        comment_count: (post.comment_count || 0) + 1,
      });
    } catch (ex) {
      setCommentErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setSubmitting(false);
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
        <div className="mx-auto max-w-[880px] px-5 py-10">
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

  return (
    <CommunityPageShell>
      <div className="mx-auto max-w-[880px] space-y-5 px-5 py-6 animate-fade-up">
        <CommunityBackLink />

        <CommunityPanel>
          <header className="border-b border-slate-100 px-6 py-6 sm:px-8">
            <SectionPill section={post.section} label={post.section_label} />
            <h1 className="mt-4 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
              {post.title}
            </h1>
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm text-slate-500">
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
                <span className="inline-flex items-center gap-1">
                  <Star className="h-3.5 w-3.5" />
                  {post.favorite_count ?? 0}
                </span>
              </div>
              <button
                type="button"
                disabled={favBusy}
                onClick={() => void onToggleFavorite()}
                className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition active:scale-[0.98] ${
                  post.favorited
                    ? "border-amber-200 bg-amber-50 text-amber-700"
                    : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                }`}
              >
                <Star
                  className={`h-4 w-4 ${post.favorited ? "fill-amber-500 text-amber-500" : ""}`}
                />
                {post.favorited ? "已收藏" : "收藏"}
              </button>
            </div>
          </header>

          <div className="px-6 py-8 text-[15px] leading-8 text-slate-700 whitespace-pre-wrap sm:px-8">
            {post.body || "（无正文）"}
          </div>

          {post.code_snippet ? (
            <div className="border-t border-slate-100 px-6 py-5 sm:px-8">
              <div className="overflow-hidden rounded-xl border border-slate-200 bg-slate-950">
                <div className="flex items-center justify-between border-b border-slate-800 px-4 py-2">
                  <span className="text-xs font-medium tracking-wide text-slate-400">
                    CODE
                  </span>
                  <span className="text-[11px] text-slate-500">片段</span>
                </div>
                <pre className="overflow-x-auto p-4 text-xs leading-relaxed text-slate-100">
                  <code>{post.code_snippet}</code>
                </pre>
              </div>
            </div>
          ) : null}

          <footer className="border-t border-slate-100 bg-slate-50/80 px-6 py-3 text-xs text-slate-400 sm:px-8">
            内容仅供学习交流，不构成投资建议。
          </footer>
        </CommunityPanel>

        <CommunityPanel>
          <div className="border-b border-slate-100 px-5 py-3.5">
            <h2 className="text-sm font-bold text-slate-900">
              评论 {comments.length > 0 ? `· ${comments.length}` : ""}
            </h2>
          </div>

          <ul className="divide-y divide-slate-100">
            {comments.length === 0 && (
              <li className="px-5 py-10 text-center text-sm text-slate-400">
                还没有评论，来抢沙发
              </li>
            )}
            {comments.map((c) => {
              const name = c.author.display_name || c.author.username || "匿名";
              return (
                <li key={c.id} className="px-5 py-4">
                  <div className="flex gap-3">
                    <AuthorAvatar name={name} size="md" />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
                        <span className="font-medium text-slate-700">{name}</span>
                        <span>{formatPostTime(c.created_at)}</span>
                      </div>
                      <p className="mt-1.5 rounded-xl bg-slate-50 px-3.5 py-2.5 text-sm leading-relaxed text-slate-700 whitespace-pre-wrap">
                        {c.body}
                      </p>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>

          <form
            onSubmit={onSubmitComment}
            className="border-t border-slate-100 bg-gradient-to-b from-slate-50/80 to-white px-5 py-4"
          >
            {user ? (
              <>
                <textarea
                  className={fieldClassName("min-h-[96px] resize-y")}
                  placeholder="写下你的看法…"
                  value={commentBody}
                  onChange={(e) => setCommentBody(e.target.value)}
                  maxLength={2000}
                />
                {commentErr && (
                  <p className="mt-2 text-sm text-red-600">{commentErr}</p>
                )}
                <div className="mt-3 flex justify-end">
                  <PrimaryButton
                    type="submit"
                    disabled={submitting || !commentBody.trim()}
                  >
                    {submitting ? "发送中…" : "发表评论"}
                  </PrimaryButton>
                </div>
              </>
            ) : (
              <p className="text-sm text-slate-500">
                <Link
                  to={`/login?next=${encodeURIComponent(`/community/post/${post.id}`)}`}
                  className="font-medium text-red-600 hover:underline"
                >
                  登录
                </Link>
                后即可评论
              </p>
            )}
          </form>
        </CommunityPanel>
      </div>
    </CommunityPageShell>
  );
}
