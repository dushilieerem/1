/** Reuse research functions in either product without exchanging identity tokens. */
import * as personal from "./auth";
import { clearQuantSession, getQuantSession, isQuantPath, subscribeQuantAuth } from "./quantAuth";
export function inQuantWorkspace() { return typeof window !== "undefined" && isQuantPath(window.location.pathname); }
export function getStoredUser(): personal.AuthUser | null {
 if (!inQuantWorkspace()) return personal.getStoredUser();
 const u = getQuantSession()?.user;
 return u ? { ...u, role: "quant_researcher", status: u.status || "active" } : null;
}
export function researchIdentity() {
 if (!inQuantWorkspace()) return "personal:" + (personal.getStoredUser()?.id || "");
 const s = getQuantSession(); return "quant:" + (s?.org.id || "") + ":" + (s?.user.id || "") + ":" + (s?.token || "");
}
export function authHeaders(): Record<string, string> {
 if (!inQuantWorkspace()) return Object.fromEntries(new Headers(personal.authHeaders()).entries());
 const s = getQuantSession(); return s ? { Authorization: "Bearer " + s.token } : {};
}
export function assertAuthConsistency() {
 if (!inQuantWorkspace()) return personal.assertAuthConsistency();
 if (!getQuantSession()) throw new Error("请登录机构量化平台");
}
export function subscribeAuth(fn: () => void) {
 const a = personal.subscribeAuth(fn), b = subscribeQuantAuth(fn);
 return () => { a(); b(); };
}
export function prepareAuthHandoff() {
 // A same-origin window.open inherits sessionStorage; no shared quant token handoff.
 if (!inQuantWorkspace()) personal.prepareAuthHandoff();
}
export function researchPagePath(path: string) {
 if (!inQuantWorkspace()) return path;
 if (path === "/factor/detect") return "/quant/factor/reports";
 return path.replace(/^\/factor\/detect(?=\/|$)/, "/quant/factor")
  .replace(/^\/strategy\/research(?=\/|$)/, "/quant/strategy")
  .replace(/^\/(factor|strategy)\/library(?=\/|$)/, "/quant/$1/library");
}
const protectedPaths = [
 /^\/strategy-research\/topics(?:\/[^/]+(?:\/(ledger|branches))?)?$/,
 /^\/factor-workflow\/projects\/[^/]+\/iterations(?:\/latest)?$/,
 /^\/factor-workflow\/iterations\/[^/]+(?:\/pause)?$/,
 /^\/factor-workflow\/agent-jobs(?:\/[^/]+(?:\/cancel)?)?$/,
 /^\/factor-workflow\/overview$/,
 /^\/factor-workflow\/imports\/svquant-existing(?:\/reference)?$/,
 /^\/factor-workflow\/projects\/[^/]+\/topics$/,
 /^\/factor-workflow\/topics$/, 
 /^\/factor-workflow\/topics\/[^/]+(?:\/(ledger|threshold|branches|trials|handback|pause|resume|f0-runs))?$/,
 /^\/factor-workflow\/topics\/[^/]+\/branches\/[^/]+\/(takeover|f0|activate)$/,
 /^\/factor-workflow\/f0-runs\/[^/]+(?:\/resume)?$/,
 /^\/factor-workflow\/pending-review-count$/,
 /^\/factor-workflow\/reviews(?:\/[^/]+)?$/,
 /^\/factor-workflow\/reviews\/[^/]+\/independent-opinion$/,
 /^\/factor-workflow\/projects\/[^/]+\/(candidates|assistant)$/,
 /^\/factor-workflow\/candidates\/[^/]+(?:\/(validate|cancel|archive|submit|register|review-request|sealed-validation))?$/,
 /^\/detect\/(projects|runs)(\/[^/]+)?(\/runs)?$/,
 /^\/strategy\/(projects|runs)(\/[^/]+)?(\/runs)?$/,
 /^\/factor\/libraries(\/factors|\/[^/]+(\/factors(\/[^/]+)?)?)?$/,
 /^\/strategy\/libraries(\/[^/]+(\/strategies(\/[^/]+)?)?)?$/,
 /^\/strategy\/library-strategies\/[^/]+\/(archive|mark-detected)$/,
 /^\/strategy\/library(\/[^/]+)?$/,
 /^\/ai\/(factor|strategy)-generations$/,
 /^\/backtest\/(factor|strategy)(\/[^/]+)?$/,
];
const publicReads = /^\/api\/(re\/health|factor\/(index|re-catalog|file\/[^/]+))$/;
export async function researchFetch(input: string | URL | Request, init?: RequestInit): Promise<Response> {
 if (!inQuantWorkspace()) return globalThis.fetch(input, init);
 if (input instanceof Request) throw new Error("机构研究请求必须使用明确的接口路径");
 const url = new URL(String(input), window.location.origin);
 if (url.origin !== window.location.origin) throw new Error("机构令牌不能发送到外部地址");
 const method = (init?.method || "GET").toUpperCase();
 const headers = new Headers(init?.headers);
 const identity = researchIdentity();
 if (publicReads.test(url.pathname) && method === "GET") {
   headers.delete("Authorization");
 } else {
   const relative = url.pathname.replace(/^\/api(?:\/inst\/quant)?/, "");
   if (!url.pathname.startsWith("/api/") || !protectedPaths.some(p => p.test(relative))) throw new Error("此功能未开放给机构量化工作区");
   const s = getQuantSession();
   if (!s) throw new Error("请登录机构量化平台");
   if (method !== "GET" && s.permissions.quant !== "write" && !(method === "POST" && s.permissions.quant === "review" && /^\/factor-workflow\/reviews\/[^/]+$/.test(relative))) throw new Error("当前机构角色没有写入权限");
   if (relative === "/strategy/library/sync") throw new Error("内置策略目录由平台管理");
   url.pathname = "/api/inst/quant" + relative;
   headers.set("Authorization", "Bearer " + s.token);
 }
 const response = await globalThis.fetch(url.pathname + url.search, { ...init, headers, cache: "no-store" });
 if (identity !== researchIdentity()) throw new Error("研究身份已变化，已丢弃旧请求结果");
 if (response.status === 401 && !publicReads.test(url.pathname)) clearQuantSession();
 return response;
}
