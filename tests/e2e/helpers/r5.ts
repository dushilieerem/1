import { APIRequestContext, Page } from "@playwright/test";

/** R5 E2E 公共助手。所有测试数据带 R5_TEST_ 前缀；凭据不入库不入报告。 */

export const FE = process.env.R5_FE_BASE || "http://localhost:9530";
export const KH = process.env.R5_KH_BASE || "http://localhost:9531";
export const API = process.env.R5_API_BASE || "http://127.0.0.1:8766";
export const RUN_ID = process.env.R5_RUN_ID || `R5_TEST_${Math.floor(Date.now() / 1000)}`;
const EPOCH = (RUN_ID.match(/\d{5,}/) || [String(Date.now())])[0].slice(-8);

export const USER_A = `R5_TEST_a_${EPOCH}`;
export const USER_B = `R5_TEST_b_${EPOCH}`;
export const USER_C = `R5_TEST_c_${EPOCH}`;
export const PW = "R5Test123!";
export const ADMIN_USER = process.env.R5_ADMIN_USER || "admin";
export const ADMIN_PW = process.env.R5_ADMIN_PASSWORD || "admin123";

export type Sess = { username: string; password: string; token: string };
export type ApiRes = { status: number; json: any };

export async function api(
  request: APIRequestContext,
  method: string,
  path: string,
  opts: { token?: string | null; body?: unknown } = {},
): Promise<ApiRes> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (opts.token) headers["Authorization"] = `Bearer ${opts.token}`;
  const resp = await request.fetch(API + path, {
    method,
    headers,
    data: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    timeout: 60_000,
  });
  let json: any = null;
  try {
    json = await resp.json();
  } catch {
    /* non-json body */
  }
  return { status: resp.status(), json };
}

export async function registerUser(request: APIRequestContext, username: string, password: string): Promise<Sess> {
  const r = await api(request, "POST", "/api/auth/register", { body: { username, password } });
  if (r.status === 400 && String(r.json?.error || "").includes("用户名已存在")) {
    return loginUser(request, username, password);
  }
  if (r.status !== 200 || !r.json?.token) {
    throw new Error(`register ${username} failed: HTTP ${r.status} ${JSON.stringify(r.json).slice(0, 200)}`);
  }
  return { username, password, token: r.json.token };
}

export async function loginUser(request: APIRequestContext, username: string, password: string): Promise<Sess> {
  const r = await api(request, "POST", "/api/auth/login", { body: { username, password } });
  if (r.status !== 200 || !r.json?.token) {
    throw new Error(`login ${username} failed: HTTP ${r.status}`);
  }
  return { username, password, token: r.json.token };
}

/** RE 依赖步骤的前置探测：不可达时调用方应 blockStep()。 */
export async function reUp(request: APIRequestContext): Promise<boolean> {
  try {
    const r = await api(request, "GET", "/api/re/health");
    return r.status === 200;
  } catch {
    return false;
  }
}

/** RE 不可达时的统一处理：标注 BLOCKED 并跳过（报告中按 BLOCKED 统计，不计 FAIL）。 */
export async function blockStep(info: { annotations: { type: string; description: string }[] }, reason: string): Promise<never> {
  info.annotations.push({ type: "BLOCKED", description: reason });
  throw new SkipError(reason);
}

export class SkipError extends Error {}

/** 浏览器内以登录态 fetch 前端同源 /api（经 vite 代理到后端），用于事务步骤的真实前端链路。 */
export async function pageFetch(
  page: Page,
  method: string,
  path: string,
  token: string | null,
  body?: unknown,
): Promise<{ status: number; json: any }> {
  return page.evaluate(
    async ({ method, path, token, body }) => {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(path, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      let json: any = null;
      try {
        json = await res.json();
      } catch {
        /* non-json */
      }
      return { status: res.status, json };
    },
    { method, path, token, body } as { method: string; path: string; token: string | null; body?: unknown },
  );
}

/** 主前端登录页登录（表单结构：第一个 input=用户名，input[type=password]=密码）。 */
export async function loginUi(page: Page, username: string, password: string) {
  await page.goto(FE + "/login");
  const form = page.locator('input[type="password"]').first().locator("xpath=ancestor::form[1]");
  const userInput = form.locator("input").first();
  await userInput.fill(username);
  await form.locator('input[type="password"]').fill(password);
  await form.getByRole("button").click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20_000 });
}

export async function sessionOf(page: Page): Promise<{ token: string | null; user: any }> {
  return page.evaluate(() => {
    const token = sessionStorage.getItem("svquant_token");
    const raw = sessionStorage.getItem("svquant_user");
    return { token, user: raw ? JSON.parse(raw) : null };
  });
}

export function noSecretLeak(json: any): boolean {
  const raw = JSON.stringify(json ?? "").toLowerCase();
  return !["password_hash", "jwt_secret", "api_key", "apikey=", "secret="].some((s) => raw.includes(s));
}
