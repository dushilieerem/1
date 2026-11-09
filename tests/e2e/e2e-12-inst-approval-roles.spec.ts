import { expect, test, type APIRequestContext } from "@playwright/test";

import { evaluateWriteGuard } from "./helpers/write-guard.mjs";

/**
 * v3 审批台四套角色：投资经理只读、合伙人/风控/Chairman 只在本关可操作；
 * 跨关动作由服务端拒绝；Chairman 批准后生成 AUTH 快照。
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
    const data = res.ok() ? await res.json() : { error: `HTTP ${res.status}` };
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
  const company = eligible.find((c: any) => !held.has(String(c.symbol))) || eligible[0];
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
    { mode: "full" },
  );
  const versionId = Number(research.versions[0].id);
  let lockRes = await request.post(`${API}/api/inst/research/${versionId}/lock`, {
    headers: { Authorization: `Bearer ${T.manager}` },
    data: {},
  });
  if (!lockRes.ok()) {
    lockRes = await request.post(`${API}/api/inst/research/${versionId}/lock`, {
      headers: { Authorization: `Bearer ${T.manager}` },
      data: { allow_gaps: true, comment: "E2E：带缺口锁定" },
    });
  }
  expect(lockRes.ok(), `研究锁定失败 HTTP ${lockRes.status()}`).toBeTruthy();

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
  await call(request, "POST", `/api/inst/proposals/${proposal.id}/lock`, T.manager, {
    allow_warnings: true,
  });
  return Number(proposal.id);
}

test("四套审批角色页面：当前关可操作、跨关被拒", async ({ browser, request }) => {
  test.skip(!writeEnabled, "写库用例需要 INST_E2E_ALLOW_WRITE=1 且服务端库名为 svquant_test");
  test.setTimeout(300_000);
  const proposalId = await prepareProposal(request);
  const url = `${BASE}/inst/approvals?key=${encodeURIComponent(`proposal:${proposalId}`)}`;

  // 投资经理：只读，进入合伙人关也只显示只读说明，没有审批按钮。
  const manager = await openPage(browser, T.manager);
  await manager.page.goto(url, { waitUntil: "networkidle" });
  await manager.page.locator(".v3-stepper .v3-step").nth(1).click();
  await expect(manager.page.getByText("提案人只读").first()).toBeVisible({ timeout: 20_000 });
  await expect(manager.page.getByRole("button", { name: "复核通过" })).toHaveCount(0);
  await expect(manager.page.getByRole("button", { name: "放行" })).toHaveCount(0);
  await expect(manager.page.getByRole("button", { name: /批准并生成授权/ })).toHaveCount(0);
  await manager.ctx.close();

  // 风控在合伙人通过前：页面只读，服务端拒绝跨关动作。
  const riskBefore = await openPage(browser, T.risk);
  await riskBefore.page.goto(url, { waitUntil: "networkidle" });
  await expect(riskBefore.page.getByText("该议案不在你当前角色的审批范围", { exact: false })).toBeVisible({
    timeout: 20_000,
  });
  await expect(riskBefore.page.getByRole("button", { name: "放行" })).toHaveCount(0);
  const early = await request.post(`${API}/api/inst/proposals/${proposalId}/risk-check`, {
    headers: { Authorization: `Bearer ${T.risk}` },
    data: { decision: "pass" },
  });
  expect(early.ok(), "合伙人未通过前风控放行应被服务端拒绝").toBeFalsy();
  await riskBefore.ctx.close();

  // 合伙人：只看本关字段与操作。
  const partner = await openPage(browser, T.partner);
  await partner.page.goto(url, { waitUntil: "networkidle" });
  await expect(partner.page.getByText("合伙人复核", { exact: true }).first()).toBeVisible({ timeout: 20_000 });
  await expect(partner.page.getByText("研究与辩论摘要", { exact: true }).first()).toBeVisible();
  await expect(partner.page.getByText("六项硬约束核查", { exact: false })).toHaveCount(0);
  await partner.page.getByRole("button", { name: "复核通过" }).click();
  await expect
    .poll(async () => (await call(request, "GET", `/api/inst/proposals/${proposalId}`, T.manager)).status, {
      timeout: 30_000,
    })
    .toBe("risk_precheck");
  await expect(partner.page.getByText("合伙人环节已结束或尚未轮到", { exact: false })).toBeVisible();
  await expect(partner.page.getByRole("button", { name: "复核通过" })).toHaveCount(0);
  await partner.ctx.close();

  // 风控：六项核查 + 放行。
  const risk = await openPage(browser, T.risk);
  await risk.page.goto(url, { waitUntil: "networkidle" });
  await expect(risk.page.getByText("六项硬约束核查", { exact: false }).first()).toBeVisible({ timeout: 20_000 });
  await expect(risk.page.getByText("研究与辩论摘要", { exact: false })).toHaveCount(0);
  await risk.page.getByRole("button", { name: "放行", exact: true }).click();
  await expect
    .poll(async () => (await call(request, "GET", `/api/inst/proposals/${proposalId}`, T.manager)).status, {
      timeout: 30_000,
    })
    .toBe("chairman_review");
  await risk.ctx.close();

  // Chairman：完整审批链 + 批准生成授权。
  const chairman = await openPage(browser, T.chairman);
  await chairman.page.goto(url, { waitUntil: "networkidle" });
  await expect(chairman.page.getByText("完整审批链", { exact: true }).first()).toBeVisible({ timeout: 20_000 });
  await expect(chairman.page.getByText("研究与辩论摘要", { exact: true }).first()).toBeVisible();
  await expect(chairman.page.getByText("风控结论", { exact: true }).first()).toBeVisible();
  await expect(chairman.page.getByText("六项硬约束核查", { exact: false })).toHaveCount(0);
  await expect(chairman.page.getByRole("button", { name: /批准并生成授权/ })).toBeVisible();
  await chairman.page.getByRole("button", { name: /批准并生成授权/ }).click();
  await expect(chairman.page.getByText("授权文件 AUTH", { exact: true })).toBeVisible({ timeout: 30_000 });
  const detail = await call(request, "GET", `/api/inst/proposals/${proposalId}`, T.manager);
  expect(detail.status).toBe("authorized");
  expect(detail.authorization?.status).toBe("qualified");
  await expect(chairman.page.getByText(/授权 ID/)).toBeVisible();
  await chairman.ctx.close();
});
