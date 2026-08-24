/** 与 SVQuant 共用 token；支持 handoff 与直登。 */

export type AuthUser = {
  id: number;
  username: string;
  role: string;
  display_name?: string;
  status?: string;
};

const TOKEN_KEY = "svquant_token";
const USER_KEY = "svquant_user";
const HANDOFF_KEY = "svquant_auth_handoff";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function setSession(token: string, user: AuthUser) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export function bootstrapAuth() {
  try {
    const raw = localStorage.getItem(HANDOFF_KEY);
    if (!raw) return;
    localStorage.removeItem(HANDOFF_KEY);
    const data = JSON.parse(raw) as {
      token?: string;
      user?: AuthUser | string;
      t?: number;
      exp?: number;
    };
    if (data.t != null && Date.now() - data.t > 60_000) return;
    if (data.exp && Date.now() > data.exp) return;
    if (!data.token || !data.user) return;
    const user =
      typeof data.user === "string"
        ? (JSON.parse(data.user) as AuthUser)
        : data.user;
    setSession(data.token, user);
  } catch {
    /* ignore */
  }
}

export async function login(username: string, password: string) {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = (await res.json()) as {
    token?: string;
    user?: AuthUser;
    error?: string;
  };
  if (!res.ok || !data.token || !data.user) {
    throw new Error(data.error || `登录失败 HTTP ${res.status}`);
  }
  if (data.user.role !== "admin") {
    throw new Error("仅管理员可进入知识库平台");
  }
  setSession(data.token, data.user);
  return data.user;
}

export async function fetchMe(): Promise<AuthUser | null> {
  const res = await fetch("/api/auth/me", { headers: { ...authHeaders() } });
  if (!res.ok) return null;
  const data = (await res.json()) as { user?: AuthUser };
  if (data.user) {
    localStorage.setItem(USER_KEY, JSON.stringify(data.user));
  }
  return data.user || null;
}
