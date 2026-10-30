/**
 * 机构端会话：与个人版登录态完全分离（不同 storage key、不同接口、不同令牌 scope）。
 * 机构令牌由 `/api/inst/auth/login` 签发，只能访问 `/api/inst/*`。
 */
export type InstAccess = "write" | "read" | "digest" | "none";

export type InstWorkspace = {
  key: string;
  label_cn: string;
  label_en: string;
  path: string;
  access: InstAccess;
  visible: boolean;
};

export type InstOrg = {
  id: number;
  code: string;
  name_cn: string;
  name_en?: string;
};

export type InstUser = {
  id: number;
  username: string;
  display_name?: string;
  role?: string;
};

export type InstSession = {
  token: string;
  user: InstUser;
  org: InstOrg;
  role: string;
  role_label_cn: string;
  role_label_en: string;
  permissions: Record<string, InstAccess>;
  workspaces: InstWorkspace[];
  demo: boolean;
  dev_skip_auth?: boolean;
};

const TOKEN_KEY = "svquant_inst_token";
const SESSION_KEY = "svquant_inst_session";

function store(): Storage {
  return sessionStorage;
}

export function getInstToken(): string | null {
  try {
    return store().getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getInstSession(): InstSession | null {
  try {
    const raw = store().getItem(SESSION_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as InstSession;
  } catch {
    return null;
  }
}

export function setInstSession(session: InstSession): void {
  const s = store();
  s.setItem(TOKEN_KEY, session.token);
  s.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearInstSession(): void {
  try {
    store().removeItem(TOKEN_KEY);
    store().removeItem(SESSION_KEY);
  } catch {
    /* ignore */
  }
}

function parseSession(data: unknown): InstSession {
  const obj = (data || {}) as Partial<InstSession> & { token?: string };
  if (!obj.token || !obj.user || !obj.org || !obj.role) {
    throw new Error("机构端登录响应异常");
  }
  return obj as InstSession;
}

async function readError(res: Response): Promise<string> {
  const data = (await res.json().catch(() => ({}))) as { error?: string };
  return data.error || `HTTP ${res.status}`;
}

export async function instLogin(username: string, password: string): Promise<InstSession> {
  const res = await fetch("/api/inst/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error(await readError(res));
  const session = parseSession(await res.json());
  setInstSession(session);
  return session;
}

/** 用机构令牌换当前会话；401 视为会话失效并清理 */
export async function fetchInstMe(): Promise<InstSession | null> {
  const token = getInstToken();
  if (!token) return null;
  const res = await fetch("/api/inst/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 401) {
    clearInstSession();
    return null;
  }
  if (!res.ok) throw new Error(await readError(res));
  const data = (await res.json()) as unknown as InstSession & { ok?: boolean };
  if (!data || !data.user) return null;
  const session: InstSession = { ...data, token };
  setInstSession(session);
  return session;
}

export function instLogout(): void {
  clearInstSession();
}
