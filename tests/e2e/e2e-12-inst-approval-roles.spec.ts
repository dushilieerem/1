import { expect, test, type APIRequestContext } from "@playwright/test";

import { evaluateWriteGuard } from "./helpers/write-guard.mjs";

/**
 * 审批台四套角色页面：投资经理只读、合伙人/风控/Chairman 各自只看本关
 * 与本角色 Agent；跨角色直接打开议案应显示无权限。
 */
const BASE = process.env.INST_BASE || "http://127.0.0.1:9533";
const API = process.env.INST_API || "http://127.0.0.1:8771";
const PW = process.env.INST_PASSWORD || "inst123456";
const ALLOW_WRITE = process.env.INST_E2E_ALLOW_WRITE === "1";

let writeEnabled = false;
const T: Record<string, string> = {};

async function login(request: APIRequestContext, username: string): Promise<string> {
  const res = await request.post(`${API}/api/inst/auth/login`, {
    data: { username, password: PW },
  });
  expect(res.ok(), `登录失败 ${username} HTTP ${res.status()}`).toBeTruthy();
  return (await res.json()).token;
}

async function call(
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
): Promise<{ ctx: import("@playwright/test").BrowserContext; page: import("@playwright/test").Page }> {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await ctx.addInitScript((t) => sessionStorage.setItem("svquant_inst_token", t), token);
  const page = await ctx.newPage();
  return { ctx, page };
}

test.beforeAll(async ({ request }) => {
  for (const role of ["manager", "partner", "risk", "chairman"]) {
    T[role] = await login(request, `inst_${role}`);
  }
  if (ALLOW_WRITE) {
    const res = await request.get(`${API}/api/inst/_e2e/guard`, {
      headers: { Authorization: `Bearer ${T.manager}` },
    });
    const data = res.ok() ? await res.json() : { error: `HTTP ${res.status()}` };
    const guard = evaluateWriteGuard({ allowWrite: true, guardResponse: data });
    if (guard.fatal) throw new Error(guard.fatal);
    writeEnabled = guard.enabled;
  }
});

async function prepareProposal(request: APIRequestContext): Promise<number> {
  const portfolio = await call(request, "GET", "/api/inst/portfolio", T.manager);
  const positions = (portfolio.positions || []).filter((p: any) => Number(p.qty) > 0);
  const held = new Set(positions.map((p: any) => String(p.symbol)));
  const crowded = new Set(
    positions
      .filter((p: any) => Number(p.weight || 0) > 0.2 && p.industry)
      .map((p: any) => String(p.industry)),
  );
  const companies = await call(request, "GET", "/api/inst/companies?limit=200", T.manager);
  const eligible = (companies.items || []).filter(
    (c: any) =>
      c.market === "CN" &&
      Number(c.ref_price) >= 5 &&
      c.data_status === "real" &&
      c.up_down_status === "非涨跌停" &&
      !c.is_st &&
      !c.is_suspended &&
      !crowded.has(String(c.industry || "")),
  );
  // 本用例不成交，已持仓标的也可复用；优先未持仓，避免重复运行后无候选。
  const company =
    eligible.find((c: any) => !held.has(String(c.symbol))) || eligible[0];
  expect(company, "找不到可用于审批角色测试的标的").toBeTruthy();

  const created = await call(request, "POST", "/api/inst/cases", T.manager, {
    company_id: Number(company.id),
  });
  const caseId = Number(created.id);
  const research = await call(
    request,
    "POST",
    `/api/inst/cases/${caseId}/research`,
    T.manager,
    { mode: "valuation" },
  );
  const versionId = Number(research.versions[0].id);
  await call(request, "POST", `/api/inst/research/${versionId}/review`, T.partner, {
    decision: "approve",
    comment: "审批角色测试",
  });
  await call(request, "POST", `/api/inst/cases/${caseId}/debate`, T.manager, { use_ai: false });
  const proposal = await call(request, "POST", `/api/inst/cases/${caseId}/proposals`, T.manager, {
    direction: "buy",
    target_weight: 0.02,
    price_low: 1,
    price_high: 100000,
    funding_source: "现金",
    valid_until: "2099-12-31",
    monitoring: ["季度财报后复核"],
    investment_opinion: "审批角色测试：关键假设成立才持有",
  });
  // 用 1-100000 的宽价格带，避免行情波动导致风控价格项否决。
  return Number(proposal.id);
}

test("四套审批角色页面：可见字段、Agent 与跨角色权限", async ({ browser, request }) => {
  test.skip(!writeEnabled, "写库用例需要 INST_E2E_ALLOW_WRITE=1 且服务端库名为 svquant_test");
  test.setTimeout(300_000);
  const proposalId = await prepareProposal(request);

  // 投资经理：只读，只有议案 + 三关进度，没有审批按钮与任何 Agent。
  const manager = await openPage(browser, T.manager);
  await manager.page.goto(`${BASE}/inst/approvals?proposal=${proposalId}`, {
    waitUntil: "networkidle",
  });
  await expect(manager.page.getByText("提案人只读").first()).toBeVisible({ timeout: 20_000 });
  await expect(manager.page.getByText("审批进度").first()).toBeVisible();
  await expect(manager.page.getByText("合伙人 Agent", { exact: false })).toHaveCount(0);
  await expect(manager.page.getByText("六项硬约束核查", { exact: false })).toHaveCount(0);
  await manager.ctx.close();

  // 合伙人：研究与辩论摘要 + 合伙人 Agent；没有风控六项明细。
  const partner = await openPage(browser, T.partner);
  await partner.page.goto(`${BASE}/inst/approvals?proposal=${proposalId}`, {
    waitUntil: "networkidle",
  });
  await expect(partner.page.getByText("研究与辩论摘要").first()).toBeVisible({ timeout: 20_000 });
  await expect(partner.page.getByText("合伙人 Agent · 审批建议").first()).toBeVisible();
  await expect(partner.page.getByText("六项硬约束核查", { exact: false })).toHaveCount(0);
  await partner.ctx.close();

  // 风控在合伙人通过前直接打开 → 无权限。
  const riskBefore = await openPage(browser, T.risk);
  await riskBefore.page.goto(`${BASE}/inst/approvals?proposal=${proposalId}`, {
    waitUntil: "networkidle",
  });
  await expect(riskBefore.page.getByText("该议案不在你当前角色的审批范围").first()).toBeVisible({
    timeout: 20_000,
  });
  await riskBefore.ctx.close();

  await call(request, "POST", `/api/inst/proposals/${proposalId}/partner`, T.partner, {
    decision: "approve",
  });

  const risk = await openPage(browser, T.risk);
  await risk.page.goto(`${BASE}/inst/approvals?proposal=${proposalId}`, { waitUntil: "networkidle" });
  await expect(risk.page.getByText("六项硬约束核查").first()).toBeVisible({ timeout: 20_000 });
  await expect(risk.page.getByText("风控 Agent · 审批建议").first()).toBeVisible();
  await expect(risk.page.getByText("研究与辩论摘要", { exact: false })).toHaveCount(0);
  const partnerAfter = await openPage(browser, T.partner);
  await partnerAfter.page.goto(`${BASE}/inst/approvals?proposal=${proposalId}`, {
    waitUntil: "networkidle",
  });
  await expect(partnerAfter.page.getByText("提案人只读", { exact: false })).toHaveCount(0);
  await partnerAfter.ctx.close();

  await call(request, "POST", `/api/inst/proposals/${proposalId}/risk-check`, T.risk, {
    decision: "pass",
  });

  const chairman = await openPage(browser, T.chairman);
  await chairman.page.goto(`${BASE}/inst/approvals?proposal=${proposalId}`, {
    waitUntil: "networkidle",
  });
  await expect(chairman.page.getByText("完整审批链").first()).toBeVisible({ timeout: 20_000 });
  await expect(chairman.page.getByText("风控结论").first()).toBeVisible();
  await expect(chairman.page.getByText("Chairman Agent · 决策建议").first()).toBeVisible();
  await expect(chairman.page.getByText("六项硬约束核查", { exact: false })).toHaveCount(0);
  await chairman.ctx.close();
  await risk.ctx.close();
});
