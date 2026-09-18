import { authHeaders, getStoredUser, patchStoredUser } from "@/lib/auth";
import type { CommunityPost } from "@/lib/communityApi";

export type UserProfile = {
  id: number;
  username: string;
  display_name: string;
  role?: string;
  avatar_url?: string | null;
  cover_url?: string | null;
  headline?: string;
  bio?: string;
  created_at?: string | null;
  following_count: number;
  followers_count: number;
  post_count: number;
  is_self: boolean;
  is_following: boolean;
};

export type FollowListUser = {
  id: number;
  username: string;
  display_name: string;
  avatar_url?: string | null;
  headline?: string;
  post_count?: number;
  followers_count?: number;
  following_count?: number;
  is_following: boolean;
  is_self: boolean;
};

async function readJson<T>(res: Response): Promise<T> {
  const data = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (!res.ok) {
    throw new Error((data as { error?: string }).error || `HTTP ${res.status}`);
  }
  return data;
}

export async function getUserProfile(username: string) {
  const res = await fetch(`/api/users/${encodeURIComponent(username)}`, {
    headers: { ...authHeaders() },
  });
  return readJson<{ ok: boolean; profile: UserProfile }>(res);
}

export async function listUserPosts(
  username: string,
  opts?: { limit?: number; offset?: number; section?: string },
) {
  const q = new URLSearchParams();
  if (opts?.limit != null) q.set("limit", String(opts.limit));
  if (opts?.offset != null) q.set("offset", String(opts.offset));
  if (opts?.section && opts.section !== "all") q.set("section", opts.section);
  const qs = q.toString();
  const res = await fetch(
    `/api/users/${encodeURIComponent(username)}/posts${qs ? `?${qs}` : ""}`,
    { headers: { ...authHeaders() } },
  );
  return readJson<{
    ok: boolean;
    total: number;
    section?: string;
    section_counts?: Record<string, number>;
    items: CommunityPost[];
  }>(res);
}

export async function listUserFollows(
  username: string,
  kind: "following" | "followers",
  opts?: { limit?: number; offset?: number },
) {
  const q = new URLSearchParams();
  if (opts?.limit != null) q.set("limit", String(opts.limit));
  if (opts?.offset != null) q.set("offset", String(opts.offset));
  const qs = q.toString();
  const res = await fetch(
    `/api/users/${encodeURIComponent(username)}/${kind}${qs ? `?${qs}` : ""}`,
    { headers: { ...authHeaders() } },
  );
  return readJson<{
    ok: boolean;
    kind: string;
    total: number;
    items: FollowListUser[];
  }>(res);
}

export async function updateMyProfile(payload: {
  display_name?: string;
  headline?: string;
  bio?: string;
  avatar_url?: string | null;
  cover_url?: string | null;
}) {
  const res = await fetch("/api/profile/me", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  const data = await readJson<{ ok: boolean; profile: UserProfile }>(res);
  if (getStoredUser() && data.profile) {
    patchStoredUser({
      display_name: data.profile.display_name,
      avatar_url: data.profile.avatar_url,
      cover_url: data.profile.cover_url,
      headline: data.profile.headline,
      bio: data.profile.bio,
    });
  }
  return data;
}

export async function followUser(username: string) {
  const res = await fetch(
    `/api/users/${encodeURIComponent(username)}/follow`,
    { method: "POST", headers: { ...authHeaders() } },
  );
  return readJson<{ ok: boolean; profile: UserProfile }>(res);
}

export async function unfollowUser(username: string) {
  const res = await fetch(
    `/api/users/${encodeURIComponent(username)}/follow`,
    { method: "DELETE", headers: { ...authHeaders() } },
  );
  return readJson<{ ok: boolean; profile: UserProfile }>(res);
}
