import { authHeaders } from "@/lib/auth";

export type AdminUser = {
  id: number;
  username: string;
  email?: string | null;
  role: string;
  status: string;
  display_name?: string | null;
  created_at?: string | null;
};

export type AdminUserList = {
  ok: boolean;
  items: AdminUser[];
  total: number;
  limit: number;
  offset: number;
};

async function json<T>(res: Response): Promise<T> {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
  return data as T;
}

export async function listAdminUsers(params: {
  q?: string;
  status?: string;
  role?: string;
  limit?: number;
  offset?: number;
}): Promise<AdminUserList> {
  const q = new URLSearchParams();
  if (params.q) q.set("q", params.q);
  if (params.status) q.set("status", params.status);
  if (params.role) q.set("role", params.role);
  q.set("limit", String(params.limit ?? 50));
  q.set("offset", String(params.offset ?? 0));
  return json<AdminUserList>(await fetch(`/api/admin/users?${q.toString()}`, { headers: { ...authHeaders() } }));
}

export async function setAdminUserStatus(id: number, status: string): Promise<void> {
  await json(await fetch(`/api/admin/users/${id}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ status }),
  }));
}

export async function setAdminUserRole(id: number, role: string): Promise<void> {
  await json(await fetch(`/api/admin/users/${id}/role`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ role }),
  }));
}

export async function resetAdminUserPassword(id: number, password: string): Promise<void> {
  await json(await fetch(`/api/admin/users/${id}/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ password }),
  }));
}
