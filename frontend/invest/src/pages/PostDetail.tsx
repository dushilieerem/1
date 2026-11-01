import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Bookmark, Flag, Heart, MessageSquare } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Disclaimer, ErrorState, LoadingCards, PageHeader, Sheet, Tag } from "../components";

type Post = {
  id: number;
  section: string;
  section_label: string;
  title: string;
  body: string;
  view_count: number;
  comment_count: number;
  like_count: number;
  favorited?: boolean;
  my_vote?: number | null;
  created_at?: string;
  author?: { username?: string; display_name?: string; avatar_url?: string };
};

type Comment = {
  id: number;
  body: string;
  created_at?: string;
  author?: { username?: string; display_name?: string };
  parent_id?: number | null;
};

export default function PostDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const postId = Number(id);
  const [post, setPost] = useState<Post | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [reportTarget, setReportTarget] = useState<{ type: "post" | "comment"; id: number } | null>(null);
  const [reportReason, setReportReason] = useState("spam");
  const [reportDetail, setReportDetail] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const load = () => {
    setError(null);
    Promise.all([
      api<{ post?: Post } & Post>(`/api/community/posts/${postId}`).then((d) => d.post || (d as Post)),
      api<{ items: Comment[] }>(`/api/community/posts/${postId}/comments?limit=50`).then((d) => d.items || []),
    ])
      .then(([p, c]) => {
        setPost(p);
        setComments(c);
      })
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    if (postId) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [postId]);

  const submit = async () => {
    if (!user) {
      nav("/login");
      return;
    }
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/api/community/posts/${postId}/comments`, {
        method: "POST",
        body: JSON.stringify({ body: text.trim() }),
      });
      setText("");
      load();
    } catch (e: any) {
      setError(e.message || "回复失败");
    } finally {
      setBusy(false);
    }
  };

  const like = async () => {
    if (!user) {
      nav("/login");
      return;
    }
    try {
      await api(`/api/community/posts/${postId}/vote`, {
        method: "POST",
        body: JSON.stringify({ value: post?.my_vote === 1 ? 0 : 1 }),
      });
      load();
    } catch (e: any) {
      setError(e.message || "操作失败");
    }
  };

  const openReport = (type: "post" | "comment", id: number) => {
    if (!user) {
      nav("/login");
      return;
    }
    setReportTarget({ type, id });
    setReportOpen(true);
  };

  const submitReport = async () => {
    if (!reportTarget) return;
    setBusy(true);
    setError(null);
    try {
      await api("/api/community/reports", {
        method: "POST",
        body: JSON.stringify({
          target_type: reportTarget.type,
          post_id: reportTarget.type === "post" ? reportTarget.id : postId,
          comment_id: reportTarget.type === "comment" ? reportTarget.id : undefined,
          reason: reportReason,
          detail: reportDetail,
        }),
      });
      setReportOpen(false);
      setReportDetail("");
      setNotice("举报已提交，我们会尽快处理。");
    } catch (e: any) {
      setError(e.message || "举报失败");
    } finally {
      setBusy(false);
    }
  };

  const favorite = async () => {
    if (!user) {
      nav("/login");
      return;
    }
    try {
      if (post?.favorited) {
        await api(`/api/community/posts/${postId}/favorite`, { method: "DELETE" });
      } else {
        await api(`/api/community/posts/${postId}/favorite`, { method: "POST" });
      }
      load();
    } catch (e: any) {
      setError(e.message || "操作失败");
    }
  };

  if (error && !post) {
    return (
      <div className="page">
        <PageHeader title="帖子" back onBack={() => nav(-1)} />
        <ErrorState message={error} onRetry={load} />
      </div>
    );
  }

  if (!post) {
    return (
      <div className="page">
        <PageHeader title="帖子" back onBack={() => nav(-1)} />
        <LoadingCards rows={3} />
      </div>
    );
  }

  return (
    <div className="page">
      <PageHeader title="社区帖子" back onBack={() => nav(-1)} right={<Tag tone="gray">{post.section_label}</Tag>} />

      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {notice ? <div className="callout blue">{notice}</div> : null}

      <article className="card">
        <h2 style={{ fontSize: 19, lineHeight: 1.4, fontWeight: 700 }}>{post.title}</h2>
        <div className="post-row-meta" style={{ marginTop: 6 }}>
          <span>{post.author?.display_name || post.author?.username || "匿名"}</span>
          <span>· {post.created_at?.slice(0, 10)}</span>
          <span>· {post.view_count} 阅读</span>
        </div>
        <p className="post-body" style={{ marginTop: 12 }}>{post.body}</p>
        <div className="post-row-stats" style={{ marginTop: 14 }}>
          <button className="chip" onClick={like} aria-label="点赞">
            <Heart size={13} /> {post.like_count}
          </button>
          <button className="chip" onClick={favorite} aria-label="收藏">
            <Bookmark size={13} /> {post.favorited ? "已收藏" : "收藏"}
          </button>
          <span className="chip">
            <MessageSquare size={13} /> {post.comment_count}
          </span>
          <button className="chip" onClick={() => openReport("post", post.id)} aria-label="举报帖子">
            <Flag size={13} /> 举报
          </button>
        </div>
      </article>

      <section className="card">
        <h3 style={{ fontSize: 14, fontWeight: 700 }}>评论 {comments.length}</h3>
        {comments.length ? (
          <div>
            {comments.map((c) => (
              <div key={c.id} className="comment-item">
                <div className="comment-meta">
                  {c.author?.display_name || c.author?.username || "匿名"} · {c.created_at?.slice(0, 16).replace("T", " ")}
                </div>
                <div className="comment-text">{c.body}</div>
                <button className="chip" style={{ marginTop: 6 }} onClick={() => openReport("comment", c.id)}>
                  举报
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className="hint">还没有评论，来说两句。</p>
        )}

        <div style={{ marginTop: 12 }}>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={2000}
            placeholder={user ? "写下你的看法…" : "登录后可参与讨论"}
            disabled={!user}
            style={{ width: "100%", minHeight: 86, padding: 10, borderRadius: 10, border: "1px solid var(--line)", fontSize: 13 }}
          />
          <button className="btn btn-primary w100" disabled={busy || !text.trim()} onClick={submit} style={{ marginTop: 8 }}>
            {busy ? "发送中…" : "发表评论"}
          </button>
        </div>
      </section>

      <Sheet
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        title="举报内容"
        sub="请选择原因；恶意举报会被记录"
        footer={
          <button className="btn btn-primary w100" disabled={busy} onClick={submitReport}>
            {busy ? "提交中…" : "提交举报"}
          </button>
        }
      >
        <label className="field">
          <span>原因</span>
          <select value={reportReason} onChange={(e) => setReportReason(e.target.value)}>
            <option value="spam">垃圾广告</option>
            <option value="abuse">辱骂骚扰</option>
            <option value="illegal">违法违规</option>
            <option value="misinfo">不实信息</option>
            <option value="other">其他</option>
          </select>
        </label>
        <label className="field">
          <span>补充说明（可选）</span>
          <textarea
            value={reportDetail}
            onChange={(e) => setReportDetail(e.target.value)}
            maxLength={500}
            placeholder="请描述问题"
            style={{ minHeight: 80 }}
          />
        </label>
      </Sheet>

      <Disclaimer>社区内容为用户观点，不构成投资建议。</Disclaimer>
    </div>
  );
}
