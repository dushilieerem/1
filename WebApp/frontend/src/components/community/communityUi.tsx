import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";
import { Eye, MessageCircle, Star } from "lucide-react";
import {
  formatPostTime,
  sectionBar,
  type CommunityPost,
} from "@/lib/communityApi";

export function sectionBadgeClass(section: string): string {
  const map: Record<string, string> = {
    official: "bg-sky-50 text-sky-700 ring-sky-100",
    strategy: "bg-violet-50 text-violet-700 ring-violet-100",
    factor: "bg-emerald-50 text-emerald-700 ring-emerald-100",
    qa: "bg-amber-50 text-amber-700 ring-amber-100",
    hotspot: "bg-orange-50 text-orange-700 ring-orange-100",
  };
  return map[section] ?? "bg-slate-100 text-slate-600 ring-slate-200";
}

export function SectionPill({
  section,
  label,
}: {
  section: string;
  label: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${sectionBadgeClass(section)}`}
    >
      {label}
    </span>
  );
}

export function AuthorAvatar({
  name,
  size = "sm",
  title,
  onDoubleClick,
}: {
  name: string;
  size?: "sm" | "md";
  title?: string;
  onDoubleClick?: () => void;
}) {
  const letter = (name || "?").slice(0, 1).toUpperCase();
  const dim = size === "md" ? "h-8 w-8 text-xs" : "h-5 w-5 text-[10px]";
  const interactive = Boolean(onDoubleClick);
  return (
    <span
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      title={title}
      onDoubleClick={onDoubleClick}
      onKeyDown={
        interactive
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onDoubleClick?.();
              }
            }
          : undefined
      }
      className={`inline-flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-slate-200 to-slate-300 font-semibold text-slate-700 ${dim} ${
        interactive
          ? "cursor-pointer outline-none ring-offset-1 hover:ring-2 hover:ring-red-200 focus-visible:ring-2 focus-visible:ring-red-300"
          : ""
      }`}
      aria-hidden={!interactive}
      aria-label={interactive ? title || `插入 @${name}` : undefined}
    >
      {letter}
    </span>
  );
}

export function HotRankBadge({ rank }: { rank: number }) {
  const top = rank <= 3;
  return (
    <span
      className={`inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-[11px] font-bold ${
        top
          ? "bg-gradient-to-br from-orange-400 to-red-500 text-white shadow-sm shadow-orange-200/60"
          : "bg-slate-100 text-slate-400"
      }`}
    >
      {rank}
    </span>
  );
}

export function CommunityPageShell({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`community-shell relative min-h-[calc(100vh-4rem)] ${className}`}
    >
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-56 bg-gradient-to-b from-red-50/80 via-[#f3f5f8] to-transparent"
        aria-hidden
      />
      <div className="relative">{children}</div>
    </div>
  );
}

export function CommunityPanel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_rgba(15,23,42,0.04)] ${className}`}
    >
      {children}
    </div>
  );
}

export function CommunityBackLink({
  to = "/community",
  label = "返回社区",
}: {
  to?: string;
  label?: string;
}) {
  return (
    <Link
      to={to}
      className="inline-flex items-center gap-1 text-sm text-slate-500 transition hover:text-red-600"
    >
      <span aria-hidden>←</span>
      {label}
    </Link>
  );
}

export function PrimaryButton({
  children,
  className = "",
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type={type}
      {...props}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg bg-red-500 px-4 py-2 text-sm font-semibold text-white shadow-sm shadow-red-200/50 transition hover:bg-red-400 active:scale-[0.98] disabled:opacity-60 ${className}`}
    >
      {children}
    </button>
  );
}

export function fieldClassName(extra = "") {
  return `w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-red-300 focus:ring-2 focus:ring-red-100 ${extra}`;
}

export function PostListItem({
  post,
  showAuthor = true,
}: {
  post: CommunityPost;
  showAuthor?: boolean;
}) {
  const authorName =
    post.author.display_name || post.author.username || "匿名";
  return (
    <Link
      to={`/community/post/${post.id}`}
      className="community-post-row group block px-5 py-5 transition hover:bg-slate-50/90"
    >
      <div className="flex flex-wrap items-center gap-2">
        <SectionPill section={post.section} label={post.section_label} />
        <h2 className="text-base font-semibold tracking-tight text-slate-900 transition group-hover:text-red-600">
          {post.title}
        </h2>
      </div>
      <div className="mt-3.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
        {showAuthor && (
          <span className="inline-flex items-center gap-1.5 text-slate-500">
            <AuthorAvatar name={authorName} />
            {authorName}
          </span>
        )}
        <span>发布于 {formatPostTime(post.created_at)}</span>
        <span className="inline-flex items-center gap-1">
          <Eye className="h-3.5 w-3.5" />
          {post.view_count}
        </span>
        <span className="inline-flex items-center gap-1">
          <MessageCircle className="h-3.5 w-3.5" />
          {post.comment_count ?? 0}
        </span>
        <span className="inline-flex items-center gap-1">
          <Star className="h-3.5 w-3.5" />
          {post.favorite_count ?? 0}
        </span>
      </div>
    </Link>
  );
}

export function SectionDot({ sectionId }: { sectionId: string }) {
  return (
    <span
      className={`h-2 w-2 shrink-0 rounded-full ${sectionBar(sectionId)}`}
      aria-hidden
    />
  );
}
