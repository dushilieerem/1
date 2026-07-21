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

function sectionBadge(section: string) {
  const map: Record<string, string> = {
    official: "bg-sky-50 text-sky-700",
    strategy: "bg-violet-50 text-violet-700",
    factor: "bg-emerald-50 text-emerald-700",
    qa: "bg-amber-50 text-amber-700",
    hotspot: "bg-orange-50 text-orange-700",
  };
  return map[section] ?? "bg-slate-100 text-slate-600";
}

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
      <div className="min-h-[calc(100vh-4rem)] bg-[#f3f5f8] px-5 py-16 text-center text-sm text-slate-500">
        加载中…
      </div>
    );
  }

  if (err || !post) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-[#f3f5f8] px-5 py-10">
        <div className="mx-auto max-w-[880px]">
          <Link to="/community" className="text-sm text-slate-500 hover:text-red-600">
            ← 返回社区
          </Link>
          <p className="mt-4 rounded border border-red-100 bg-white px-4 py-3 text-sm text-red-600">
            {err || "帖子不存在"}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-[#f3f5f8]">
      <div className="mx-auto max-w-[880px] space-y-4 px-5 py-6">
        <Link to="/community" className="text-sm text-slate-500 hover:text-red-600">
          ← 返回社区
        </Link>

        <article className="overflow-hidden rounded border border-slate-200 bg-white shadow-sm shadow-slate-200/40">
          <header className="border-b border-slate-100 px-6 py-5">
            <span
              className={`inline-block rounded px-1.5 py-0.5 text-[11px] font-medium ${sectionBadge(post.section)}`}
            >
              {post.section_label}
            </span>
            <h1 className="mt-3 text-2xl font-bold tracking-tight text-slate-900">
              {post.title}
            </h1>
            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-500">
              <span className="font-medium text-slate-700">
                {post.author.display_name || post.author.username || "匿名"}
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
            <div className="mt-4">
              <button
                type="button"
                disabled={favBusy}
                onClick={() => void onToggleFavorite()}
                className={`inline-flex items-center gap-1.5 rounded border px-3 py-1.5 text-sm font-medium transition ${
                  post.favorited
                    ? "border-amber-200 bg-amber-50 text-amber-700"
                    : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                }`}
              >
                <Star className={`h-4 w-4 ${post.favorited ? "fill-amber-500 text-amber-500" : ""}`} />
                {post.favorited ? "已收藏" : "收藏"}
              </button>
            </div>
          </header>

          <div className="px-6 py-6 whitespace-pre-wrap text-[15px] leading-7 text-slate-700">
            {post.body || "（无正文）"}
          </div>

          {post.code_snippet ? (
            <div className="border-t border-slate-100 px-6 py-5">
              <h2 className="mb-2 text-sm font-semibold text-slate-800">代码</h2>
              <pre className="overflow-x-auto rounded border border-slate-200 bg-slate-50 p-4 text-xs leading-relaxed text-slate-800">
                <code>{post.code_snippet}</code>
              </pre>
            </div>
          ) : null}

          <footer className="border-t border-slate-100 bg-slate-50 px-6 py-3 text-xs text-slate-400">
            内容仅供学习交流，不构成投资建议。
          </footer>
        </article>

        <section className="overflow-hidden rounded border border-slate-200 bg-white shadow-sm shadow-slate-200/40">
          <div className="border-b border-slate-100 px-5 py-3">
            <h2 className="text-sm font-bold text-slate-900">
              评论 {comments.length > 0 ? `· ${comments.length}` : ""}
            </h2>
          </div>

          <ul className="divide-y divide-slate-100">
            {comments.length === 0 && (
              <li className="px-5 py-8 text-center text-sm text-slate-400">还没有评论，来抢沙发</li>
            )}
            {comments.map((c) => (
              <li key={c.id} className="px-5 py-4">
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <span className="font-medium text-slate-700">
                    {c.author.display_name || c.author.username || "匿名"}
                  </span>
                  <span>{formatPostTime(c.created_at)}</span>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
                  {c.body}
                </p>
              </li>
            ))}
          </ul>

          <form onSubmit={onSubmitComment} className="border-t border-slate-100 bg-slate-50 px-5 py-4">
            {user ? (
              <>
                <textarea
                  className="min-h-[88px] w-full resize-y rounded border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-red-300 focus:ring-1 focus:ring-red-200"
                  placeholder="写下你的看法…"
                  value={commentBody}
                  onChange={(e) => setCommentBody(e.target.value)}
                  maxLength={2000}
                />
                {commentErr && (
                  <p className="mt-2 text-sm text-red-600">{commentErr}</p>
                )}
                <div className="mt-3 flex justify-end">
                  <button
                    type="submit"
                    disabled={submitting || !commentBody.trim()}
                    className="rounded bg-red-500 px-4 py-2 text-sm font-semibold text-white hover:bg-red-400 disabled:opacity-60"
                  >
                    {submitting ? "发送中…" : "发表评论"}
                  </button>
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
        </section>
      </div>
    </div>
  );
}
