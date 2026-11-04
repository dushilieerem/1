/** Institutional quantitative sessions never share personal/subjective token keys. */
export type QuantSession = {
 token: string; product: "quant";
 user: { id: number; username: string; display_name?: string; role?: string; status?: string };
 org: { id: number; code: string; name_cn: string };
 role?: string; can_review?: boolean; can_write?: boolean; membership?: { role?: string }; permissions: { quant: "read" | "write" | "review" };
};
const KEY = "svquant_quant_session";
const listeners = new Set<() => void>();
export const subscribeQuantAuth = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn); }; };
export function getQuantSession(): QuantSession | null {
 try { const value = JSON.parse(sessionStorage.getItem(KEY) || "null");
 return value?.product === "quant" && value?.token && value?.user?.id && value?.org?.id && ["read", "write", "review"].includes(value?.permissions?.quant) ? value : null;
 } catch { return null; }
}
export function setQuantSession(session: QuantSession) {
 if (session.product !== "quant" || !session.token || !session.org?.id || !session.user?.id) throw new Error("机构量化会话无效");
 sessionStorage.setItem(KEY, JSON.stringify(session));
 listeners.forEach(fn => fn());
}
export function clearQuantSession() { sessionStorage.removeItem(KEY); listeners.forEach(fn => fn()); }
export function isQuantPath(path: string) { return path === "/quant" || path.startsWith("/quant/"); }
export function quantLoginUrl(next = "/quant") { return "/login?mode=inst&product=quant&next=" + encodeURIComponent(isQuantPath(next.split(/[?#]/)[0]) ? next : "/quant"); }
export function safeLoginNext(next: string | null, product: "personal" | "subjective" | "quant") {
 const fallback = product === "quant" ? "/quant" : product === "subjective" ? "/inst" : "/";
 if (!next || !next.startsWith("/") || next.startsWith("//") || /[\\\x00-\x20]/.test(next)) return fallback;
 const path = new URL(next, "https://svquant.invalid").pathname;
 if (product === "quant") return isQuantPath(path) ? next : fallback;
 if (product === "subjective") return path === "/inst" || path.startsWith("/inst/") ? next : fallback;
 return isQuantPath(path) || path === "/inst" || path.startsWith("/inst/") ? fallback : next;
}
async function responseData(response: Response) {
 const data = await response.json().catch(() => ({}));
 if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : data.error || "机构量化登录失败，请检查账号权限");
 return data;
}
export async function quantLogin(username: string, password: string) {
 const data = await responseData(await fetch("/api/inst/quant/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) }));
 setQuantSession(data);
 return data as QuantSession;
}
export async function fetchQuantMe(): Promise<QuantSession> {
 const previous = getQuantSession();
 if (!previous) throw new Error("请登录机构量化平台");
 const response = await fetch("/api/inst/quant/me", { cache: "no-store", headers: { Authorization: "Bearer " + previous.token } });
 if (response.status === 401 || response.status === 403) clearQuantSession();
 const data = await responseData(response);
 if (getQuantSession()?.token !== previous.token) throw new Error("登录身份已变化，请重新进入");
 const next = { ...data, token: previous.token };
 // Don't notify research listeners for an unchanged identity refresh.
 sessionStorage.setItem(KEY, JSON.stringify(next));
 return next;
}
