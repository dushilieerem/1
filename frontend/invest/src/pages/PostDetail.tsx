import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Bookmark, Flag, Heart, MessageSquare } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Disclaimer, ErrorState, LoadingCards, PageHeader, Sheet, Tag } from "../components";
import { useLocale } from "../i18n";

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
  const { t, locale } = useLocale();
  const sectionLabel = (label: string) =>
    locale === "en"
      ? ({ 策略分享: "Strategy share", 因子笔记: "Factor notes", 问答: "Q&A", 热点分析: "Market topics", 官方: "Official" } as Record<string, string>)[label] ||
        label
      : label;
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
      setError(e.message || t("回复失败", "Reply failed"));
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
      setError(e.message || t("操作失败", "Action failed"));
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
      setNotice(t("举报已提交，我们会尽快处理。", "Report submitted; we will review it as soon as possible."));
    } catch (e: any) {
      setError(e.message || t("举报失败", "Report failed"));
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
      setError(e.message || t("操作失败", "Action failed"));
    }
  };

  if (error && !post) {
    return (
      <div className="page">
        <PageHeader title={t("帖子", "Post")} back onBack={() => nav(-1)} />
        <ErrorState message={error} onRetry={load} />
      </div>
    );
  }

  if (!post) {
    return (
      <div className="page">
        <PageHeader title={t("帖子", "Post")} back onBack={() => nav(-1)} />
        <LoadingCards rows={3} />
      </div>
    );
  }

  return (
    <div className="page">
      <PageHeader title={t("社区帖子", "Community post")} back onBack={() => nav(-1)} right={<Tag tone="gray">{sectionLabel(post.section_label)}</Tag>} />

      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {notice ? <div className="callout blue">{notice}</div> : null}

      <article className="card">
        <h2 style={{ fontSize: 19, lineHeight: 1.4, fontWeight: 700 }}>{post.title}</h2>
        <div className="post-row-meta" style={{ marginTop: 6 }}>
          <span>{post.author?.display_name || post.author?.username || t("匿名", "Anonymous")}</span>
          <span>· {post.created_at?.slice(0, 10)}</span>
          <span>· {t(`${post.view_count} 阅读`, `${post.view_count} views`)}</span>
        </div>
        <p className="post-body" style={{ marginTop: 12 }}>{post.body}</p>
        <div className="post-row-stats" style={{ marginTop: 14 }}>
          <button className="chip" onClick={like} aria-label={t("点赞", "Like")}>
            <Heart size={13} /> {post.like_count}
          </button>
          <button className="chip" onClick={favorite} aria-label={t("收藏", "Save")}>
            <Bookmark size={13} /> {post.favorited ? t("已收藏", "Saved") : t("收藏", "Save")}
          </button>
          <span className="chip">
            <MessageSquare size={13} /> {post.comment_count}
          </span>
          <button className="chip" onClick={() => openReport("post", post.id)} aria-label={t("举报帖子", "Report post")}>
            <Flag size={13} /> {t("举报", "Report")}
          </button>
        </div>
      </article>

      <section className="card">
        <h3 style={{ fontSize: 14, fontWeight: 700 }}>{t(`评论 ${comments.length}`, `Comments ${comments.length}`)}</h3>
        {comments.length ? (
          <div>
            {comments.map((c) => (
              <div key={c.id} className="comment-item">
                <div className="comment-meta">
                  {c.author?.display_name || c.author?.username || t("匿名", "Anonymous")} · {c.created_at?.slice(0, 16).replace("T", " ")}
                </div>
                <div className="comment-text">{c.body}</div>
                <button className="chip" style={{ marginTop: 6 }} onClick={() => openReport("comment", c.id)}>
                  {t("举报", "Report")}
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className="hint">{t("还没有评论，来说两句。", "No comments yet—be the first to share your thoughts.")}</p>
        )}

        <div style={{ marginTop: 12 }}>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={2000}
            placeholder={user ? t("写下你的看法…", "Write your thoughts…") : t("登录后可参与讨论", "Log in to join the discussion")}
            disabled={!user}
            style={{ width: "100%", minHeight: 86, padding: 10, borderRadius: 10, border: "1px solid var(--line)", fontSize: 13 }}
          />
          <button className="btn btn-primary w100" disabled={busy || !text.trim()} onClick={submit} style={{ marginTop: 8 }}>
            {busy ? t("发送中…", "Sending…") : t("发表评论", "Post comment")}
          </button>
        </div>
      </section>

      <Sheet
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        title={t("举报内容", "Report content")}
        sub={t("请选择原因；恶意举报会被记录", "Choose a reason; malicious reports will be recorded")}
        footer={
          <button className="btn btn-primary w100" disabled={busy} onClick={submitReport}>
            {busy ? t("提交中…", "Submitting…") : t("提交举报", "Submit report")}
          </button>
        }
      >
        <label className="field">
          <span>{t("原因", "Reason")}</span>
          <select value={reportReason} onChange={(e) => setReportReason(e.target.value)}>
            <option value="spam">{t("垃圾广告", "Spam")}</option>
            <option value="abuse">{t("辱骂骚扰", "Harassment")}</option>
            <option value="illegal">{t("违法违规", "Illegal content")}</option>
            <option value="misinfo">{t("不实信息", "Misinformation")}</option>
            <option value="other">{t("其他", "Other")}</option>
          </select>
        </label>
        <label className="field">
          <span>{t("补充说明（可选）", "Additional details (optional)")}</span>
          <textarea
            value={reportDetail}
            onChange={(e) => setReportDetail(e.target.value)}
            maxLength={500}
            placeholder={t("请描述问题", "Describe the issue")}
            style={{ minHeight: 80 }}
          />
        </label>
      </Sheet>

      <Disclaimer>{t("社区内容为用户观点，不构成投资建议。", "Community content reflects users' views and is not investment advice.")}</Disclaimer>
    </div>
  );
}
