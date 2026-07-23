import {
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  ChevronDown,
  ImagePlus,
  MessageCircle,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";
import {
  formatPostTime,
  type CommunityComment,
  voteComment,
} from "@/lib/communityApi";
import { compressImageFile } from "@/lib/imageCompress";
import { AuthorAvatar, PrimaryButton, fieldClassName } from "@/components/community/communityUi";
import { ImageLightbox } from "@/components/community/ImageLightbox";

const PREVIEW_REPLY_N = 2;
/** 评论列表缩略图固定框，避免超宽图缩成细条 / logo 显得过大 */
const THUMB_STYLE: CSSProperties = {
  width: 128,
  height: 96,
  objectFit: "cover",
  display: "block",
};

function CommentText({ text }: { text: string }) {
  const parts = text.split(/(@[\w.\u4e00-\u9fff-]+)/g);
  return (
    <p className="mt-1.5 text-sm leading-relaxed text-slate-700 whitespace-pre-wrap">
      {parts.map((part, i) =>
        part.startsWith("@") ? (
          <span key={i} className="font-semibold text-red-600">
            {part}
          </span>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </p>
  );
}

function CommentImages({ images }: { images?: string[] }) {
  const [preview, setPreview] = useState<string | null>(null);
  if (!images?.length) return null;
  return (
    <>
      <div className="mt-2 flex flex-wrap gap-2">
        {images.map((src, i) => (
          <button
            key={i}
            type="button"
            onClick={() => setPreview(src)}
            className="cursor-zoom-in overflow-hidden rounded-md border border-slate-200 bg-slate-100 p-0 shadow-sm hover:border-slate-300"
            title="点击查看大图"
            style={{ width: 128, height: 96 }}
          >
            <img src={src} alt="" style={THUMB_STYLE} />
          </button>
        ))}
      </div>
      <ImageLightbox src={preview} onClose={() => setPreview(null)} />
    </>
  );
}

function VoteBar({
  comment,
  onChanged,
  onReply,
  disabled,
}: {
  comment: CommunityComment;
  onChanged: (patch: {
    like_count: number;
    dislike_count: number;
    my_vote: number;
  }) => void;
  onReply: () => void;
  disabled?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const my = comment.my_vote ?? 0;

  const cast = async (next: 1 | -1 | 0) => {
    if (disabled || busy) return;
    setBusy(true);
    try {
      const value = my === next ? 0 : next;
      const res = await voteComment(comment.id, value as 1 | -1 | 0);
      onChanged({
        like_count: res.like_count,
        dislike_count: res.dislike_count,
        my_vote: res.my_vote,
      });
    } catch (ex) {
      window.alert(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-slate-500">
      <button
        type="button"
        disabled={disabled || busy}
        onClick={() => void cast(1)}
        className={`inline-flex items-center gap-1 transition hover:text-red-600 disabled:opacity-50 ${
          my === 1 ? "font-semibold text-red-600" : ""
        }`}
      >
        <ThumbsUp className={`h-3.5 w-3.5 ${my === 1 ? "fill-red-500" : ""}`} />
        {comment.like_count ?? 0}
      </button>
      <button
        type="button"
        disabled={disabled || busy}
        onClick={() => void cast(-1)}
        className={`inline-flex items-center gap-1 transition hover:text-slate-800 disabled:opacity-50 ${
          my === -1 ? "font-semibold text-slate-800" : ""
        }`}
      >
        <ThumbsDown className={`h-3.5 w-3.5 ${my === -1 ? "fill-slate-600" : ""}`} />
        {comment.dislike_count ?? 0}
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={onReply}
        className="inline-flex items-center gap-1 transition hover:text-red-600 disabled:opacity-50"
      >
        <MessageCircle className="h-3.5 w-3.5" />
        回复
      </button>
    </div>
  );
}

function sortByLikes(a: CommunityComment, b: CommunityComment) {
  const la = a.like_count ?? 0;
  const lb = b.like_count ?? 0;
  if (lb !== la) return lb - la;
  const ta = a.created_at || "";
  const tb = b.created_at || "";
  return ta.localeCompare(tb);
}

export function CommentThread({
  comments,
  postAuthorId,
  highlightId,
  canInteract,
  onNeedLogin,
  onCommentsChange,
  onSubmitComment,
}: {
  comments: CommunityComment[];
  postAuthorId?: number;
  highlightId?: number | null;
  canInteract: boolean;
  onNeedLogin: () => void;
  onCommentsChange: (next: CommunityComment[]) => void;
  onSubmitComment: (payload: {
    body: string;
    parentId: number | null;
    images: string[];
  }) => Promise<void>;
}) {
  const [replyTo, setReplyTo] = useState<CommunityComment | null>(null);
  const [body, setBody] = useState("");
  const [images, setImages] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const boxRef = useRef<HTMLTextAreaElement>(null);

  const roots = useMemo(() => {
    const list = comments.filter((c) => !c.parent_id);
    return [...list].sort(sortByLikes);
  }, [comments]);

  const repliesByRoot = useMemo(() => {
    const map = new Map<number, CommunityComment[]>();
    for (const c of comments) {
      if (!c.parent_id) continue;
      const list = map.get(c.parent_id) || [];
      list.push(c);
      map.set(c.parent_id, list);
    }
    for (const [k, list] of map) {
      map.set(k, [...list].sort(sortByLikes));
    }
    return map;
  }, [comments]);

  const patchComment = (
    id: number,
    patch: Partial<CommunityComment>,
  ) => {
    onCommentsChange(
      comments.map((c) => (c.id === id ? { ...c, ...patch } : c)),
    );
  };

  const startReply = (c: CommunityComment) => {
    if (!canInteract) {
      onNeedLogin();
      return;
    }
    const name = c.author.display_name || c.author.username || "用户";
    setReplyTo(c);
    setBody((prev) => (prev.trim().startsWith("@") ? prev : `@${name} `));
    requestAnimationFrame(() => {
      boxRef.current?.focus();
      boxRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  };

  const addImage = async (file: File) => {
    try {
      const src = await compressImageFile(file, { maxW: 720, maxH: 480 });
      setImages((prev) => [...prev, src].slice(0, 3));
    } catch (ex) {
      window.alert(ex instanceof Error ? ex.message : String(ex));
    }
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!canInteract) {
      onNeedLogin();
      return;
    }
    if (!body.trim() && images.length === 0) return;
    setErr(null);
    setSubmitting(true);
    try {
      let text = body.trim();
      if (replyTo) {
        const name =
          replyTo.author.display_name || replyTo.author.username || "用户";
        if (!text.includes(`@${name}`)) text = `@${name} ${text}`;
      }
      // parentId：始终传被回复评论 id，后端会压到一级
      await onSubmitComment({
        body: text,
        parentId: replyTo?.id ?? null,
        images,
      });
      setBody("");
      setImages([]);
      setReplyTo(null);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setSubmitting(false);
    }
  };

  const renderOne = (c: CommunityComment, compact?: boolean): ReactNode => {
    const name = c.author.display_name || c.author.username || "匿名";
    const isAuthor =
      postAuthorId != null && c.author.id != null && c.author.id === postAuthorId;
    const replyName = c.reply_to?.display_name || c.reply_to?.username;
    const highlighted = highlightId === c.id;
    return (
      <div
        id={`comment-${c.id}`}
        className={`rounded-lg transition ${
          highlighted ? "bg-amber-50 ring-2 ring-amber-200" : ""
        } ${compact ? "py-2" : "py-1"}`}
      >
        <div className="flex gap-2.5">
          {!compact && <AuthorAvatar name={name} size="md" />}
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
              {compact ? (
                <span className="font-medium text-slate-600">
                  {name}
                  {replyName ? (
                    <>
                      {" "}
                      <span className="font-normal text-slate-400">回复</span>{" "}
                      <span className="text-slate-700">@{replyName}</span>
                    </>
                  ) : null}
                  <span className="font-normal text-slate-400">：</span>
                </span>
              ) : (
                <>
                  <span className="font-medium text-slate-700">{name}</span>
                  {isAuthor && (
                    <span className="rounded bg-red-50 px-1.5 py-0.5 text-[10px] font-semibold text-red-600 ring-1 ring-inset ring-red-100">
                      作者
                    </span>
                  )}
                  <span>{formatPostTime(c.created_at)}</span>
                </>
              )}
            </div>
            {compact ? (
              <div className="text-sm leading-relaxed text-slate-700">
                <CommentText text={c.body} />
                <CommentImages images={c.images} />
              </div>
            ) : (
              <>
                {replyName && (
                  <p className="mt-1 text-xs text-slate-400">
                    回复 <span className="text-slate-600">@{replyName}</span>
                  </p>
                )}
                <CommentText text={c.body} />
                <CommentImages images={c.images} />
              </>
            )}
            <VoteBar
              comment={c}
              disabled={!canInteract}
              onReply={() => startReply(c)}
              onChanged={(p) => patchComment(c.id, p)}
            />
          </div>
        </div>
      </div>
    );
  };

  return (
    <div>
      <ul className="divide-y divide-slate-100">
        {roots.length === 0 && (
          <li className="px-5 py-10 text-center text-sm text-slate-400">
            还没有评论，来抢沙发
          </li>
        )}
        {roots.map((root) => {
          const replies = repliesByRoot.get(root.id) || [];
          const open = !!expanded[root.id];
          const shown = open ? replies : replies.slice(0, PREVIEW_REPLY_N);
          const hiddenN = Math.max(0, replies.length - PREVIEW_REPLY_N);
          return (
            <li key={root.id} className="px-5 py-4">
              {renderOne(root)}
              {replies.length > 0 && (
                <div className="mt-3 ml-10 rounded-xl bg-slate-50 px-3.5 py-2.5">
                  {shown.map((r) => (
                    <div key={r.id} className="border-b border-slate-100/80 last:border-0">
                      {renderOne(r, true)}
                    </div>
                  ))}
                  {hiddenN > 0 && !open && (
                    <button
                      type="button"
                      onClick={() =>
                        setExpanded((s) => ({ ...s, [root.id]: true }))
                      }
                      className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-sky-600 hover:text-sky-700"
                    >
                      共 {replies.length} 条回复
                      <ChevronDown className="h-3.5 w-3.5" />
                    </button>
                  )}
                  {open && replies.length > PREVIEW_REPLY_N && (
                    <button
                      type="button"
                      onClick={() =>
                        setExpanded((s) => ({ ...s, [root.id]: false }))
                      }
                      className="mt-1 text-xs font-medium text-slate-500 hover:text-slate-700"
                    >
                      收起
                    </button>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>

      <form
        onSubmit={onSubmit}
        className="border-t border-slate-100 bg-gradient-to-b from-slate-50/80 to-white px-5 py-4"
      >
        {canInteract ? (
          <>
            {replyTo && (
              <div className="mb-2 flex items-center justify-between rounded-lg border border-red-100 bg-red-50/70 px-3 py-2 text-xs text-red-700">
                <span>
                  回复{" "}
                  <span className="font-semibold">
                    @
                    {replyTo.author.display_name ||
                      replyTo.author.username ||
                      "用户"}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setReplyTo(null);
                    setBody((p) => p.replace(/^@\S+\s*/, ""));
                  }}
                  className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-red-100"
                >
                  <X className="h-3.5 w-3.5" />
                  取消
                </button>
              </div>
            )}
            <textarea
              ref={boxRef}
              className={fieldClassName("min-h-[88px] resize-y")}
              placeholder={
                replyTo ? "写下回复，可附图…" : "写下你的看法… 可 @用户名 或附图"
              }
              value={body}
              onChange={(e) => setBody(e.target.value)}
              onPaste={(e) => {
                const items = e.clipboardData?.items;
                if (!items) return;
                for (const item of Array.from(items)) {
                  if (item.type.startsWith("image/")) {
                    const f = item.getAsFile();
                    if (f) {
                      e.preventDefault();
                      void addImage(f);
                    }
                  }
                }
              }}
              maxLength={2000}
            />
            {images.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {images.map((src, i) => (
                  <div key={i} className="relative">
                    <img
                      src={src}
                      alt=""
                      className="h-16 w-16 rounded-lg border border-slate-200 object-cover"
                    />
                    <button
                      type="button"
                      onClick={() =>
                        setImages((prev) => prev.filter((_, j) => j !== i))
                      }
                      className="absolute -right-1.5 -top-1.5 rounded-full bg-slate-800 p-0.5 text-white"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
            {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
            <div className="mt-3 flex items-center justify-between gap-3">
              <div>
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
                >
                  <ImagePlus className="h-3.5 w-3.5" />
                  图片
                </button>
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    e.target.value = "";
                    if (f) void addImage(f);
                  }}
                />
              </div>
              <PrimaryButton
                type="submit"
                disabled={submitting || (!body.trim() && images.length === 0)}
              >
                {submitting ? "发送中…" : replyTo ? "发表回复" : "发表评论"}
              </PrimaryButton>
            </div>
          </>
        ) : (
          <p className="text-sm text-slate-500">
            <button
              type="button"
              onClick={onNeedLogin}
              className="font-medium text-red-600 hover:underline"
            >
              登录
            </button>
            后即可评论
          </p>
        )}
      </form>
    </div>
  );
}
