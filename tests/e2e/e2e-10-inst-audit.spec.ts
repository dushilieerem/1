import { expect, test, type APIRequestContext } from "@playwright/test";

import { evaluateWriteGuard } from "./helpers/write-guard.mjs";

/**
 * 主观机构端 v3 审计：九个入口、四角色菜单、控制台/5xx、窄屏、
 * 空/错/加载态、AI 一页纸缓存。默认只读；一页纸落盘需写库闸门放行。
 */
const BASE = process.env.INST_BASE || "http://127.0.0.1:9533";
const API = process.env.INST_API || "http://127.0.0.1:8771";
const PW = process.env.INST_PASSWORD || "inst123456";
// 机构端已收敛为四个角色（#211）；execution / monitoring 账号已停用。
const ROLES = ["manager", "partner", "chairman", "risk"] as const;
type Role = (typeof ROLES)[number];

const WORKSPACES: Array<[string, string]> = [
  ["/inst", "INVESTMENT OFFICE"],
  ["/inst/pipeline", "PIPELINE"],
  ["/inst/stocks", "STOCKS"],
  ["/inst/research", "RESEARCH"],
  ["/inst/debate", "DEBATE"],
  ["/inst/approvals", "DECISION"],
  ["/inst/execute", "EXECUTION"],
  ["/inst/manage", "OWNERSHIP"],
  ["/inst/playbook", "PLAYBOOK / RULES"],
];

const EXPECTED_NAV: Record<Role, string[]> = {
  manager: [
    "投资工作台",
    "项目流水线",
    "股票总览",
    "价值分析",
    "多空辩论",
    "投委会审批",
    "执行成交",
    "投资管理",
    "流程与权限",
  ],
  partner: ["投资工作台", "项目流水线", "股票总览", "投委会审批", "流程与权限"],
  risk: ["投资工作台", "项目流水线", "股票总览", "投委会审批", "流程与权限"],
  chairman: ["投资工作台", "项目流水线", "股票总览", "投委会审批", "流程与权限"],
};

const TOKENS: Partial<Record<Role, string>> = {};
const ALLOW_WRITE = process.env.INST_E2E_ALLOW_WRITE === "1";
let writeEnabled = false;
let researchCaseId: number | null = null;

async function login(request: APIRequestContext, username: string): Promise<string> {
  const res = await request.post(`${API}/api/inst/auth/login`, {
    data: { username, password: PW },
  });
  expect(res.ok(), `登录失败 ${username} HTTP ${res.status()}`).toBeTruthy();
  return (await res.json()).token;
}

async function apiCall(
  request: APIRequestContext,
  method: "GET" | "POST",
  path: string,
  token: string,
  data?: Record<string, unknown>,
): Promise<any> {
  const res = await request.fetch(`${API}${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}` },
    data,
  });
  const text = await res.text();
  if (!res.ok()) throw new Error(`${method} ${path} → ${res.status()} ${text.slice(0, 300)}`);
  return text ? JSON.parse(text) : {};
}

async function openPage(
  browser: import("@playwright/test").Browser,
  token: string,
  viewport = { width: 1440, height: 1000 },
) {
  const ctx = await browser.newContext({ viewport });
  const page = await ctx.newPage();
  await page.addInitScript((t) => sessionStorage.setItem("svquant_inst_token", t), token);
  return { ctx, page };
}

test.beforeAll(async ({ request, browser }) => {
  for (const role of ROLES) {
    TOKENS[role] = await login(request, `inst_${role}`);
  }
  const auth = { Authorization: `Bearer ${TOKENS.manager}` };
  const casesRes = await request.get(`${API}/api/inst/cases`, { headers: auth });
  const cases = casesRes.ok() ? (await casesRes.json()).items || [] : [];
  for (const c of cases.slice(0, 30)) {
    const detailRes = await request.get(`${API}/api/inst/cases/${c.id}`, { headers: auth });
    if (!detailRes.ok()) continue;
    const detail = await detailRes.json();
    if ((detail.versions || []).length) {
      researchCaseId = Number(c.id);
      break;
    }
  }

  if (ALLOW_WRITE) {
    const res = await request.get(`${API}/api/inst/_e2e/guard`, {
      headers: { Authorization: `Bearer ${TOKENS.manager}` },
    });
    const data = res.ok() ? await res.json() : { error: `HTTP ${res.status}` };
    const guard = evaluateWriteGuard({ allowWrite: true, guardResponse: data });
    if (guard.fatal) throw new Error(guard.fatal);
    writeEnabled = guard.enabled;
  }

  // 预热一次浏览器，避免首个用例把冷启动算进 console error。
  const { ctx, page } = await openPage(browser, TOKENS.manager!);
  await page.goto(`${BASE}/inst`, { waitUntil: "networkidle" });
  await ctx.close();
});

test("AI 一页纸落盘后可重复读取，不重复生成", async ({ request }) => {
  test.skip(!writeEnabled || !researchCaseId, "需要写库闸门与已有研究案");
  test.setTimeout(300_000);
  const first = await apiCall(
    request,
    "POST",
    `/api/inst/cases/${researchCaseId}/ai/memo`,
    TOKENS.manager!,
    { refresh: false },
  );
  expect(first.memo?.summary, "首次生成应有一页纸内容").toBeTruthy();
  const peek = await apiCall(
    request,
    "GET",
    `/api/inst/cases/${researchCaseId}/ai/memo`,
    TOKENS.manager!,
  );
  expect(peek.memo?.summary).toBe(first.memo.summary);
  expect(peek.cached).toBe(true);
  const again = await apiCall(
    request,
    "POST",
    `/api/inst/cases/${researchCaseId}/ai/memo`,
    TOKENS.manager!,
    { refresh: false },
  );
  expect(again.cached).toBe(true);
  expect(again.memo?.summary).toBe(first.memo.summary);
});

test("九个入口可达，无控制台错误与接口 5xx", async ({ browser }) => {
  const { ctx, page } = await openPage(browser, TOKENS.manager!);
  const errors: string[] = [];
  const failures: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(String(err)));
  page.on("response", (res) => {
    if (res.status() >= 500) failures.push(`${res.status()} ${res.url()}`);
  });

  for (const [path, text] of WORKSPACES) {
    await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
    await expect(page.getByText(text, { exact: false }).first()).toBeVisible({ timeout: 20_000 });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow, `${path} 横向溢出 ${overflow}px`).toBeLessThanOrEqual(1);
  }

  expect(errors, `控制台错误：${errors.join(" | ")}`).toEqual([]);
  expect(failures, `接口 5xx：${failures.join(" | ")}`).toEqual([]);
  await ctx.close();
});

test("四角色菜单按登录身份裁剪", async ({ browser }) => {
  for (const role of ROLES) {
    const { ctx, page } = await openPage(browser, TOKENS[role]!);
    await page.goto(`${BASE}/inst`, { waitUntil: "networkidle" });
    await expect(page.locator("aside.v3-side nav.v3-nav a span")).toHaveText(EXPECTED_NAV[role]);
    await expect(page.locator(".v3-role")).toBeVisible();
    await ctx.close();
  }
});

test("窄屏 1024 九个入口无横向溢出", async ({ browser }) => {
  const { ctx, page } = await openPage(browser, TOKENS.manager!, { width: 1024, height: 900 });
  for (const [path, text] of WORKSPACES) {
    await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
    await expect(page.getByText(text, { exact: false }).first()).toBeVisible({ timeout: 20_000 });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow, `${path} 窄屏横向溢出 ${overflow}px`).toBeLessThanOrEqual(1);
  }
  await ctx.close();
});

test("错误态：接口 500 显示错误", async ({ browser }) => {
  const { ctx, page } = await openPage(browser, TOKENS.manager!);
  await page.route("**/api/inst/portfolio*", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "模拟接口故障" }),
    }),
  );
  await page.goto(`${BASE}/inst/manage`, { waitUntil: "networkidle" });
  await expect(page.getByText(/模拟接口故障/)).toBeVisible({ timeout: 20_000 });
  await ctx.close();
});

test("加载态：投资管理先显示加载提示", async ({ browser }) => {
  const { ctx, page } = await openPage(browser, TOKENS.manager!);
  await page.route("**/api/inst/portfolio*", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.continue();
  });
  const nav = page.goto(`${BASE}/inst/manage`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText(/正在加载投资管理/)).toBeVisible({ timeout: 5_000 });
  await nav;
  await ctx.close();
});
