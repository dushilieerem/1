import { authHeaders } from "@/lib/auth";

export type AuditLogItem = {
  id: number;
  createdAt?: string | null;
  userId?: number | null;
  username?: string | null;
  role?: string | null;
  action: string;
  module?: string | null;
  resource?: string | null;
  method?: string | null;
  path?: string | null;
  statusCode?: number | null;
  durationMs?: number | null;
  ip?: string | null;
  detail?: string | null;
  requestId?: string | null;
};

export type AuditLogList = {
  total: number;
  limit: number;
  offset: number;
  items: AuditLogItem[];
};

export type AuditLogQuery = {
  limit?: number;
  offset?: number;
  module?: string;
  username?: string;
  action?: string;
  statusCode?: number;
  statusMin?: number;
  statusMax?: number;
  method?: string;
  writeOnly?: boolean;
  path?: string;
  since?: string;
  until?: string;
};

async function readJson<T>(res: Response): Promise<T> {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail =
      typeof data?.detail === "string"
        ? data.detail
        : Array.isArray(data?.detail)
          ? data.detail.map((x: { msg?: string }) => x.msg || JSON.stringify(x)).join("; ")
          : res.statusText;
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return data as T;
}

function toSearchParams(params: AuditLogQuery): URLSearchParams {
  const q = new URLSearchParams();
  if (params.limit != null) q.set("limit", String(params.limit));
  if (params.offset != null) q.set("offset", String(params.offset));
  if (params.module) q.set("module", params.module);
  if (params.username) q.set("username", params.username);
  if (params.action) q.set("action", params.action);
  if (params.statusCode != null) q.set("statusCode", String(params.statusCode));
  if (params.statusMin != null) q.set("statusMin", String(params.statusMin));
  if (params.statusMax != null) q.set("statusMax", String(params.statusMax));
  if (params.method) q.set("method", params.method);
  if (params.writeOnly) q.set("writeOnly", "true");
  if (params.path) q.set("path", params.path);
  if (params.since) q.set("since", params.since);
  if (params.until) q.set("until", params.until);
  return q;
}

export async function listAdminAuditLogs(
  params: AuditLogQuery = {},
): Promise<AuditLogList> {
  const q = toSearchParams(params);
  const res = await fetch(`/api/admin/logs?${q.toString()}`, {
    headers: { ...authHeaders() },
  });
  return readJson<AuditLogList>(res);
}
