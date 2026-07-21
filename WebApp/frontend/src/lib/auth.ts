export type AuthUser = {
  id: number;
  username: string;
  email?: string | null;
  role: string;
  status: string;
  display_name?: string;
  ai_quota_daily?: number;
  created_at?: string | null;
};

const TOKEN_KEY = "svquant_token";
const USER_KEY = "svquant_user";

type AuthListener = () => void;
const listeners = new Set<AuthListener>();

/**
 * 登录态放在 sessionStorage：每个浏览器标签页独立账号。
 * 多开标签测 admin/max/maruixiang 时不会互相覆盖 token，
 * 也不会出现「顶栏显示 A、请求却用 B 的令牌」。
 */
function authStore(): Storage {
  return sessionStorage;
}

/** 一次性从旧版 localStorage 迁到本标签 sessionStorage，并清掉共享污染源 */
function migrateAuthFromLocalStorage() {
  try {
    const ss = sessionStorage;
    if (ss.getItem(TOKEN_KEY)) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
      return;
    }
    const token = localStorage.getItem(TOKEN_KEY);
    const user = localStorage.getItem(USER_KEY);
    if (token && user) {
      ss.setItem(TOKEN_KEY, token);
      ss.setItem(USER_KEY, user);
    }
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  } catch {
    /* ignore */
  }
}

migrateAuthFromLocalStorage();

function notify() {
  listeners.forEach((fn) => fn());
}

export function subscribeAuth(fn: AuthListener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function getToken(): string | null {
  try {
    return authStore().getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getStoredUser(): AuthUser | null {
  try {
    const raw = authStore().getItem(USER_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function setSession(token: string, user: AuthUser) {
  const store = authStore();
  store.setItem(TOKEN_KEY, token);
  store.setItem(USER_KEY, JSON.stringify(user));
  // 清掉可能残留的共享 localStorage，避免其它标签误读
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  } catch {
    /* ignore */
  }
  notify();
}

export function clearSession() {
  try {
    authStore().removeItem(TOKEN_KEY);
    authStore().removeItem(USER_KEY);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  } catch {
    /* ignore */
  }
  notify();
}

export function authHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function tokenSubUserId(): number | null {
  const t = getToken();
  if (!t) return null;
  try {
    const mid = t.split(".")[1];
    if (!mid) return null;
    const json = atob(mid.replace(/-/g, "+").replace(/_/g, "/"));
    const payload = JSON.parse(json) as { sub?: string | number };
    const n = Number(payload.sub);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

/** token.sub 与本地 user.id 必须一致，否则清会话 */
export function assertAuthConsistency(): void {
  const user = getStoredUser();
  const tid = tokenSubUserId();
  if (user?.id != null && tid != null && user.id !== tid) {
    clearSession();
    throw new Error("登录态错乱（用户与令牌不一致），请重新登录");
  }
}

async function parseJson(res: Response) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data as { error?: string }).error || `HTTP ${res.status}`);
  }
  return data as { ok?: boolean; user?: AuthUser; token?: string; error?: string; dev_skip_auth?: boolean };
}

export async function login(username: string, password: string) {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await parseJson(res);
  if (!data.token || !data.user) throw new Error("登录响应异常");
  setSession(data.token, data.user);
  return data.user;
}

export async function register(payload: {
  username: string;
  password: string;
  email?: string;
  display_name?: string;
}) {
  const res = await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await parseJson(res);
  if (!data.token || !data.user) throw new Error("注册响应异常");
  setSession(data.token, data.user);
  return data.user;
}

export async function fetchMe(): Promise<AuthUser | null> {
  const token = getToken();
  if (!token) return null;
  assertAuthConsistency();
  const res = await fetch("/api/auth/me", { headers: { ...authHeaders() } });
  if (res.status === 401) {
    clearSession();
    return null;
  }
  const data = await parseJson(res);
  if (data.user) {
    const next = JSON.stringify(data.user);
    const prev = authStore().getItem(USER_KEY);
    // 内容不变不 notify，避免页面 subscribeAuth → refresh → fetchMe 死循环
    if (prev !== next) {
      authStore().setItem(USER_KEY, next);
      notify();
    }
    return data.user;
  }
  return null;
}

export function logout() {
  clearSession();
}
