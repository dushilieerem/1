import { expect, test, type APIRequestContext } from "@playwright/test";

import { evaluateWriteGuard } from "./helpers/write-guard.mjs";

/**
 * 机构端展示与可用性审计：七个工作区、六角色、窄屏、空态/错误态/加载态、
 * 控制台错误与接口 5xx。默认只读；创建空研究案的用例需写库闸门放行。
 */
const BASE = process.env.INST_BASE || "http://127.0.0.1:9533";
const API = process.env.INST_API || "http://127.0.0.1:8771";
const PW = process.env.INST_PASSWORD || "inst123456";
const ROLES = ["manager", "partner", "chairman", "risk", "execution", "monitoring"] as const;
type Role = (typeof ROLES)[number];

const WORKSPACES: Array<[string, string]> = [
  ["/inst/overview", "INVESTMENT OFFICE / 01"],
  ["/inst/ideas", "DISCOVERY / 02"],
  ["/inst/research", "RESEARCH / 03"],
  ["/inst/debate", "DEBATE / 04"],
  ["/inst/approvals", "APPROVALS / 06"],
  ["/inst/portfolio", "PORTFOLIO / 05"],
  ["/inst/about", "AGENTS / 09"],
];

const TOKENS: Partial<Record<Role, string>> = {};
const ALLOW_WRITE = process.env.INST_E2E_ALLOW_WRITE === "1";
let writeEnabled = false;
let researchCaseId: number | null = null;
let debateCaseId: number | null = null;
let proposalId: number | null = null;

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
    if (!researchCaseId && (detail.versions || []).length) researchCaseId = Number(c.id);
    if (!debateCaseId && (detail.debates || []).some((d: any) => d.status === "completed")) {
      debateCaseId = Number(c.id);
    }
    if (researchCaseId && debateCaseId) break;
  }
  const propsRes = await request.get(`${API}/api/inst/proposals`, { headers: auth });
  const props = propsRes.ok() ? (await propsRes.json()).items || [] : [];
  proposalId = props.length ? Number(props[0].id) : null;

  if (ALLOW_WRITE) {
    const res = await request.get(`${API}/api/inst/_e2e/guard`, {
      headers: { Authorization: `Bearer ${TOKENS.manager}` },
    });
    const data = res.ok() ? await res.json() : { error: `HTTP ${res.status()}` };
    const guard = evaluateWriteGuard({ allowWrite: true, guardResponse: data });
    if (guard.fatal) throw new Error(guard.fatal);
    writeEnabled = guard.enabled;
  }
  // 预热一次浏览器，避免首个用例把冷启动算进 console error。
  const { ctx, page } = await openPage(browser, TOKENS.manager!);
  await page.goto(`${BASE}/inst/overview`, { waitUntil: "networkidle" });
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

test("七个工作区可达，无控制台错误与接口 5xx", async ({ browser }) => {
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

  // 方案 B：交易执行不再是独立工作区，旧入口重定向到投资组合。
  await page.goto(`${BASE}/inst/execution`, { waitUntil: "networkidle" });
  await expect(page).toHaveURL(/\/inst\/portfolio/);
  await expect(page.getByRole("link", { name: "交易执行" })).toHaveCount(0);

  expect(errors, `控制台错误：${errors.join(" | ")}`).toEqual([]);
  expect(failures, `接口 5xx：${failures.join(" | ")}`).toEqual([]);
  await ctx.close();
});

test("详情页：研究、辩论、审批（有数据时）", async ({ browser }) => {
  test.skip(!researchCaseId && !debateCaseId && !proposalId, "测试库暂无研究/辩论/议案数据");
  const { ctx, page } = await openPage(browser, TOKENS.manager!);
  if (researchCaseId) {
    await page.goto(`${BASE}/inst/research?case=${researchCaseId}`, { waitUntil: "networkidle" });
    await expect(page.getByText("公司信息", { exact: true })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("行业分析（独立板块）", { exact: true })).toBeVisible();
    await expect(page.getByText("K 线（实时行情）", { exact: true })).toBeVisible();
    await expect(page.getByText("六维分析", { exact: true })).toBeVisible();
    await expect(page.getByText("AI 一页纸", { exact: true })).toBeVisible();
    const returnButton = page.getByRole("button", { name: /退回并重跑|Return & rerun/ });
    if (await returnButton.count()) {
      await returnButton.click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await expect(page.getByText("行业分析", { exact: true })).toBeVisible();
      await page.getByRole("button", { name: /取消|Cancel/ }).click();
    }
    const evidenceButton = page.getByRole("button", { name: /证据与反证|Evidence/ });
    await expect(evidenceButton).toBeVisible();
    await evidenceButton.click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByText("证据类型说明", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: /关闭|Close/ }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }
  if (debateCaseId) {
    // 用 partner（辩论只读）打开：manager 会触发「辩论完成自动建案」并跳转审批页。
    const partner = await openPage(browser, TOKENS.partner!);
    await partner.page.goto(`${BASE}/inst/debate?case=${debateCaseId}`, { waitUntil: "networkidle" });
    await expect(partner.page.getByText("辩论记录", { exact: false }).first()).toBeVisible({
      timeout: 20_000,
    });
    await expect(partner.page.getByText("五年 DCF", { exact: false })).toHaveCount(0);
    await partner.ctx.close();
  }
  if (proposalId) {
    await page.goto(`${BASE}/inst/approvals?proposal=${proposalId}`, { waitUntil: "networkidle" });
    await expect(page.getByText("议案详情", { exact: true })).toBeVisible({ timeout: 20_000 });
  }
  await ctx.close();
});

test("机会发现：公司卡直接展示立项研究与放弃", async ({ browser }) => {
  const { ctx, page } = await openPage(browser, TOKENS.manager!);
  await page.goto(`${BASE}/inst/ideas`, { waitUntil: "networkidle" });
  const start = page.getByRole("button", { name: /立项研究|Start research/ }).first();
  if (!(await start.count())) {
    await ctx.close();
    test.skip(true, "测试库暂无可用推送候选");
  }
  await expect(start).toBeVisible();
  await expect(page.getByRole("button", { name: /^放弃$|^Reject$/ }).first()).toBeVisible();
  await expect(page.getByText("立项三问", { exact: false })).toHaveCount(0);
  await ctx.close();
});

test("机构端：Agent 管理列表与编辑入口", async ({ browser }) => {
  const { ctx, page } = await openPage(browser, TOKENS.manager!);
  await page.goto(`${BASE}/inst/about`, { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "Agent 管理" }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/个 Agent/)).toBeVisible();
  await page.getByText("AI 一页纸", { exact: true }).first().click();
  await expect(page.locator("textarea")).toBeVisible();
  await expect(page.getByRole("button", { name: /保存提示词/ })).toBeVisible();
  await ctx.close();
});

test("窄屏 1024 七个工作区无横向溢出", async ({ browser }) => {
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

test("六角色菜单与权限边界", async ({ browser }) => {
  const expected: Record<Role, string[]> = {
    manager: ["投资总览", "机会发现", "公司研究", "投资辩论室", "投委会审批", "投资管理", "Agent管理"],
    partner: ["投资总览", "机会发现", "公司研究", "投资辩论室", "投委会审批", "投资管理", "Agent管理"],
    chairman: ["投资总览", "公司研究", "投资辩论室", "投委会审批", "投资管理", "Agent管理"],
    risk: ["投资总览", "公司研究", "投资辩论室", "投委会审批", "投资管理", "Agent管理"],
    execution: ["投资总览", "投委会审批", "投资管理", "Agent管理"],
    monitoring: ["投资总览", "公司研究", "投委会审批", "投资管理", "Agent管理"],
  };
  for (const role of ROLES) {
    const { ctx, page } = await openPage(browser, TOKENS[role]!);
    await page.goto(`${BASE}/inst/overview`, { waitUntil: "networkidle" });
    await expect(page.locator("aside nav a")).toHaveText(expected[role]);
    await ctx.close();
  }
});

test("空态：美股关注列表为空、只读角色可研究案空态", async ({ browser, request }) => {
  test.skip(!writeEnabled, "创建空研究案/清理关注列表需要 INST_E2E_ALLOW_WRITE=1 且服务端库名为 svquant_test");
  // 测试库会累计历史 e2e 关注项；先在隔离库清空，保证空态断言可重复。
  const watchRes = await request.get(`${API}/api/inst/companies?pool_status=watch&limit=100`, {
    headers: { Authorization: `Bearer ${TOKENS.manager}` },
  });
  const watchItems = watchRes.ok() ? (await watchRes.json()).items || [] : [];
  for (const item of watchItems) {
    await request.post(`${API}/api/inst/companies/${item.id}/pool`, {
      headers: { Authorization: `Bearer ${TOKENS.manager}` },
      data: { pool_status: "research" },
    });
  }
  // 美股关注列表为空（locale 切 EN 后 market=US）。
  const { ctx, page } = await openPage(browser, TOKENS.manager!, { width: 1280, height: 900 });
  await page.goto(`${BASE}/inst/overview`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /切换为英文|Switch to Chinese/ }).click();
  await page.goto(`${BASE}/inst/ideas`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Watchlist|关注与自选/ }).click();
  await expect(page.getByText(/No watchlist names|还没有关注对象/)).toBeVisible({ timeout: 20_000 });
  await ctx.close();

  const companies = await request.get(`${API}/api/inst/companies?q=600519&limit=1`, {
    headers: { Authorization: `Bearer ${TOKENS.manager}` },
  });
  const company = (await companies.json()).items?.[0];
  expect(company, "找不到 600519").toBeTruthy();
  const created = await request.post(`${API}/api/inst/cases`, {
    headers: { Authorization: `Bearer ${TOKENS.manager}` },
    data: { company_id: Number(company.id) },
  });
  expect(created.ok()).toBeTruthy();
  const caseId = (await created.json()).id;

  // 合伙人只有研究读权限，进入空研究案不会自动生成，能看到空态。
  const partner = await openPage(browser, TOKENS.partner!);
  await partner.page.goto(`${BASE}/inst/research?case=${caseId}`, { waitUntil: "networkidle" });
  await expect(partner.page.getByText("还没有研究版本。")).toBeVisible({ timeout: 20_000 });
  await partner.ctx.close();
});

test("错误态：接口 500 显示错误并可重试", async ({ browser }) => {
  const { ctx, page } = await openPage(browser, TOKENS.manager!);
  await page.route("**/api/inst/portfolio*", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "模拟接口故障" }),
    }),
  );
  await page.goto(`${BASE}/inst/portfolio`, { waitUntil: "networkidle" });
  await expect(page.getByText(/模拟接口故障/)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("button", { name: /重试|Retry/ })).toBeVisible();
  await ctx.close();
});

test("加载态：组合页先显示加载提示", async ({ browser }) => {
  const { ctx, page } = await openPage(browser, TOKENS.manager!);
  await page.route("**/api/inst/portfolio*", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.continue();
  });
  const nav = page.goto(`${BASE}/inst/portfolio`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText(/正在加载组合|Loading portfolio/)).toBeVisible({
    timeout: 5_000,
  });
  await nav;
  await ctx.close();
});
