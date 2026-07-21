import { authHeaders } from "@/lib/auth";

export type CommunitySection = "strategy" | "factor" | "qa" | "hotspot" | "official";

export type CommunityPost = {
  id: number;
  section: CommunitySection;
  section_label: string;
  title: string;
  body: string;
  code_snippet?: string | null;
  view_count: number;
  comment_count?: number;
  favorite_count?: number;
  favorited?: boolean;
  status: string;
  created_at: string | null;
  updated_at?: string | null;
  author: {
    id?: number;
    username?: string;
    display_name?: string;
  };
};

export type CommunityComment = {
  id: number;
  post_id: number;
  body: string;
  created_at: string | null;
  author: {
    id?: number;
    username?: string;
    display_name?: string;
  };
};

export const SECTION_META: {
  id: CommunitySection | "all";
  label: string;
  bar: string;
}[] = [
  { id: "all", label: "全部", bar: "bg-slate-400" },
  { id: "strategy", label: "策略分享", bar: "bg-sky-500" },
  { id: "factor", label: "因子笔记", bar: "bg-emerald-500" },
  { id: "qa", label: "问答", bar: "bg-amber-500" },
  { id: "hotspot", label: "热点分析", bar: "bg-orange-500" },
  { id: "official", label: "官方", bar: "bg-red-500" },
];

export function sectionBar(section: string) {
  return SECTION_META.find((s) => s.id === section)?.bar ?? "bg-slate-400";
}

async function parseJson<T>(res: Response): Promise<T> {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data as { error?: string }).error || `HTTP ${res.status}`);
  }
  return data as T;
}

export async function listCommunityPosts(opts?: {
  section?: string;
  limit?: number;
  offset?: number;
}) {
  const q = new URLSearchParams();
  if (opts?.section && opts.section !== "all") q.set("section", opts.section);
  if (opts?.limit != null) q.set("limit", String(opts.limit));
  if (opts?.offset != null) q.set("offset", String(opts.offset));
  const qs = q.toString();
  const res = await fetch(`/api/community/posts${qs ? `?${qs}` : ""}`);
  return parseJson<{
    ok: boolean;
    total: number;
    items: CommunityPost[];
    sections: { id: string; label: string }[];
  }>(res);
}

export async function listHotPosts(limit = 10) {
  const res = await fetch(`/api/community/hot?limit=${limit}`);
  return parseJson<{ ok: boolean; items: CommunityPost[] }>(res);
}

export async function getCommunityPost(id: number, opts?: { bump?: boolean }) {
  const bump = opts?.bump !== false;
  const q = bump ? "" : "?bump=0";
  const res = await fetch(`/api/community/posts/${id}${q}`, {
    headers: { ...authHeaders() },
  });
  return parseJson<{ ok: boolean; post: CommunityPost }>(res);
}

/** 同一会话同一帖只计 1 次浏览（避免 React StrictMode 双挂载 +2） */
export function takeViewBump(postId: number): boolean {
  try {
    const key = `svq_post_view_${postId}`;
    if (sessionStorage.getItem(key)) return false;
    sessionStorage.setItem(key, "1");
    return true;
  } catch {
    return true;
  }
}

export async function createCommunityPost(payload: {
  title: string;
  body: string;
  section: CommunitySection;
  code_snippet?: string;
}) {
  const res = await fetch("/api/community/posts", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(payload),
  });
  return parseJson<{ ok: boolean; post: CommunityPost }>(res);
}

export async function listComments(postId: number) {
  const res = await fetch(`/api/community/posts/${postId}/comments`);
  return parseJson<{ ok: boolean; total: number; items: CommunityComment[] }>(res);
}

export async function createComment(postId: number, body: string) {
  const res = await fetch(`/api/community/posts/${postId}/comments`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({ body }),
  });
  return parseJson<{ ok: boolean; comment: CommunityComment }>(res);
}

export async function addFavorite(postId: number) {
  const res = await fetch(`/api/community/posts/${postId}/favorite`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: "{}",
  });
  return parseJson<{ ok: boolean; favorited: boolean; favorite_count: number }>(res);
}

export async function removeFavorite(postId: number) {
  const res = await fetch(`/api/community/posts/${postId}/favorite`, {
    method: "DELETE",
    headers: { ...authHeaders() },
  });
  return parseJson<{ ok: boolean; favorited: boolean; favorite_count: number }>(res);
}

export async function listMyFavorites(opts?: { limit?: number; offset?: number }) {
  const q = new URLSearchParams();
  if (opts?.limit != null) q.set("limit", String(opts.limit));
  if (opts?.offset != null) q.set("offset", String(opts.offset));
  const qs = q.toString();
  const res = await fetch(`/api/community/favorites${qs ? `?${qs}` : ""}`, {
    headers: { ...authHeaders() },
  });
  return parseJson<{ ok: boolean; total: number; items: CommunityPost[] }>(res);
}

export async function listMyPosts(opts?: { limit?: number; offset?: number }) {
  const q = new URLSearchParams();
  if (opts?.limit != null) q.set("limit", String(opts.limit));
  if (opts?.offset != null) q.set("offset", String(opts.offset));
  const qs = q.toString();
  const res = await fetch(`/api/community/my-posts${qs ? `?${qs}` : ""}`, {
    headers: { ...authHeaders() },
  });
  return parseJson<{ ok: boolean; total: number; items: CommunityPost[] }>(res);
}

export function formatPostTime(iso: string | null | undefined) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function excerpt(text: string, max = 120) {
  const t = text.replace(/\s+/g, " ").trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max)}…`;
}
