import { expect, test, type APIRequestContext } from "@playwright/test";

import { evaluateWriteGuard } from "./helpers/write-guard.mjs";

/**
 * v3 执行成交 + 投资管理 UI：
 * 已持仓标的卖出议案 → AUTH → 核对/下单/对账/持仓 → 记录预警 → 创建退出研究案。
 * 写库用例：INST_E2E_ALLOW_WRITE=1，服务端 guard 必须是 svquant_test。
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

test.beforeAll(async ({ request }) => {
  // 机构端只有四个角色；执行成交由 manager 承担（后端 execute_authorization 校验 role=manager）。
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

async function pickHeld(request: APIRequestContext): Promise<any> {
  const pf = await call(request, "GET", "/api/inst/portfolio", T.manager);
  const candidates = (pf.positions || []).filter(
    (p: any) => Number(p.qty) > 1000 && p.company_id && p.symbol,
  );
  // 已关联退出议案的旧案不能再立议案（"该退出研究案已关联议案"），换一个有持仓的标的。
  const all = await call(request, "GET", "/api/inst/cases", T.manager);
  const caseByCompany = new Map<number, any>(
    (all.items || []).map((c: any) => [Number(c.company_id), c]),
  );
  for (const pos of candidates) {
    const kase = caseByCompany.get(Number(pos.company_id));
    if (!kase) return pos;
    const detail = await call(request, "GET", `/api/inst/cases/${kase.id}`, T.manager);
    if (!detail?.exit_case?.proposal_id) return pos;
  }
  expect(candidates[0], "测试库没有可卖持仓").toBeTruthy();
  throw new Error("可卖持仓都已关联退出议案，无法重复执行 e2e-14（需要重置测试库）");
}

test("执行 UI 与投资者管理：下单/对账/预警/退出研究", async ({ page, request }) => {
  test.skip(!writeEnabled, "写库用例需要 INST_E2E_ALLOW_WRITE=1 且服务端库名为 svquant_test");
  test.setTimeout(300_000);

  const pos = await pickHeld(request);
  const symbol = String(pos.symbol);
  const beforeQty = Number(pos.qty);
  // 卖出权重按"最多卖掉一半持仓"收敛：整仓卖光后投资管理页就没有持仓可挂预警了。
  const pf = await call(request, "GET", "/api/inst/portfolio", T.manager);
  const nav = Number(pf.nav || 0);
  const px = Number(pos.last_close || 0);
  const halfLot = Math.floor(beforeQty * 0.5 / 100) * 100;
  const sellWeight =
    nav > 0 && px > 0 ? Math.min(0.01, (halfLot * px) / nav) : 0.01;

  const created = await call(request, "POST", "/api/inst/cases", T.manager, {
    company_id: Number(pos.company_id),
  });
  const caseId = Number(created.id);
  // 一股一流程：重复运行会返回已锁定的旧案，先重开再走研究（会作废旧议案与授权）。
  if (created.created === false) {
    await call(request, "POST", `/api/inst/cases/${caseId}/research/reopen`, T.manager, {
      reason: "E2E 重复运行：重开研究案",
    });
  }
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
    direction: "sell",
    target_weight: Number(sellWeight.toFixed(4)),
    price_low: 1,
    price_high: 100000,
    funding_source: "现金",
    valid_until: "2099-12-31",
    monitoring: ["退出后复核"],
    investment_opinion: "E2E 执行 UI：卖出议案",
  });
  const proposalId = Number(proposal.id);
  await call(request, "POST", `/api/inst/proposals/${proposalId}/lock`, T.manager, {
    allow_warnings: true,
  });
  await call(request, "POST", `/api/inst/proposals/${proposalId}/partner`, T.partner, {
    decision: "approve",
  });
  await call(request, "POST", `/api/inst/proposals/${proposalId}/risk-check`, T.risk, {
    decision: "pass",
  });
  await call(request, "POST", `/api/inst/proposals/${proposalId}/chairman`, T.chairman, {
    decision: "approve",
  });
  const authorized = await call(
    request,
    "POST",
    `/api/inst/proposals/${proposalId}/authorize`,
    T.chairman,
  );
  const authId = Number(authorized.authorizations[0].id);

  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(String(err)));
  await page.addInitScript((t) => sessionStorage.setItem("svquant_inst_token", t), T.manager);
  await page.goto(`${BASE}/inst/execute?key=${encodeURIComponent(`auth:${authId}`)}`, {
    waitUntil: "networkidle",
  });
  await expect(page.getByText(`授权文件 AUTH-${authId}`, { exact: false })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText("授权核对", { exact: true }).first()).toBeVisible();
  await expect(page.locator(".v3-agent-pick").filter({ hasText: "执行引擎" })).toBeVisible();
  const next = page.getByRole("button", { name: /继续下单/ });
  await expect(next).toBeEnabled();
  await next.click();
  await expect(page.getByText("下单成交", { exact: true }).first()).toBeVisible();
  await page.getByTestId("inst-execute-submit").click();
  await expect(page.getByText("执行对账", { exact: false }).first()).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("inst-reconcile").click();
  await expect(page.getByText("持仓更新", { exact: true }).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("link", { name: /进入投资管理/ })).toBeVisible();
  expect(errors, `页面错误：${errors.join(" | ")}`).toEqual([]);

  const auths = await call(request, "GET", "/api/inst/authorizations", T.manager);
  const executed = (auths.items || []).find((a: any) => Number(a.id) === authId);
  expect(executed?.status).toBe("filled");
  const pfAfter = await call(request, "GET", "/api/inst/portfolio", T.manager);
  const positionAfter = (pfAfter.positions || []).find((p: any) => p.symbol === symbol);
  expect(Number(positionAfter?.qty || 0)).toBeLessThan(beforeQty);

  // 06 投资管理：记录预警 + 创建退出研究案后自动进入 02。
  const managerPage = await page.context().newPage();
  await managerPage.addInitScript((t) => sessionStorage.setItem("svquant_inst_token", t), T.manager);
  await managerPage.goto(
    `${BASE}/inst/manage?key=${encodeURIComponent(`holding:${symbol}`)}`,
    { waitUntil: "networkidle" },
  );
  await managerPage.locator(".v3-stepper .v3-step").nth(1).click();
  await expect(managerPage.locator(".v3-agent-pick").filter({ hasText: "监控 Agent" })).toBeVisible();
  await expect(managerPage.getByTestId("inst-warning")).toBeVisible({ timeout: 20_000 });
  const warningText = `E2E 预警：复核渠道库存与批价 ${Date.now()}`;
  await managerPage.getByTestId("inst-warning").fill(warningText);
  await managerPage.getByTestId("inst-warning-submit").click();
  await expect(managerPage.getByText(warningText)).toBeVisible({
    timeout: 20_000,
  });

  await managerPage.locator(".v3-stepper .v3-step").nth(2).click();
  await managerPage.getByTestId("inst-exit-memo").fill("E2E 退出研究：论点失效，申请清仓");
  await managerPage.getByTestId("inst-exit-submit").click();
  await expect(managerPage).toHaveURL(/\/inst\/research\?key=case(%3A|:)\d+/, { timeout: 30_000 });
  await expect(managerPage.locator(".v3-page-head h1").first()).toBeVisible();
  await managerPage.close();
});
