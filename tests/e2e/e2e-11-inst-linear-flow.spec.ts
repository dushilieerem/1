import { expect, test, type APIRequestContext } from "@playwright/test";

import { evaluateWriteGuard } from "./helpers/write-guard.mjs";

/**
 * v3 线性流程：研究定稿 R3 → 辩论 P3 → 合伙人 → 风控 → Chairman
 * → 授权 AUTH → 执行成交 → 持仓与结果页。
 *
 * 只读环境 skip；写库需 INST_E2E_ALLOW_WRITE=1 且服务端 guard 返回安全库。
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
  // 机构端已收敛为四个角色（manager/partner/risk/chairman）；执行由 manager 承担。
  for (const role of ["manager", "partner", "chairman", "risk"]) {
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

async function holdingQty(request: APIRequestContext, symbol: string): Promise<number> {
  const portfolio = await call(request, "GET", "/api/inst/portfolio", T.manager);
  return (portfolio.positions || [])
    .filter((p: any) => p.symbol === symbol)
    .reduce((sum: number, p: any) => sum + Number(p.qty || 0), 0);
}

/** 优先未持仓；重复运行把候选买完后，退回加仓低权重标的。 */
async function pickCompany(request: APIRequestContext): Promise<any> {
  const portfolio = await call(request, "GET", "/api/inst/portfolio", T.manager);
  const positions = (portfolio.positions || []).filter((p: any) => Number(p.qty) > 0);
  const held = new Set(positions.map((p: any) => String(p.symbol)));
  const weightOf = new Map(
    positions.map((p: any) => [String(p.symbol), Number(p.weight || 0)]),
  );
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
      !crowded.has(String(c.industry || "")) &&
      !/(^|\*)ST|退/.test(String(c.name || "")),
  );
  const company =
    eligible.find((c: any) => !held.has(String(c.symbol))) ||
    eligible.find((c: any) => Number(weightOf.get(String(c.symbol)) || 0) + 0.05 <= 0.13);
  expect(company, "找不到可用于买入流程的标的").toBeTruthy();
  return company;
}

async function lockResearch(request: APIRequestContext, versionId: number) {
  let res = await request.post(`${API}/api/inst/research/${versionId}/lock`, {
    headers: { Authorization: `Bearer ${T.manager}` },
    data: {},
  });
  // 测试库允许带数据缺口锁定，但依然必须经过 v3 门禁并记录缺口。
  if (!res.ok()) {
    res = await request.post(`${API}/api/inst/research/${versionId}/lock`, {
      headers: { Authorization: `Bearer ${T.manager}` },
      data: { allow_gaps: true, comment: "E2E：带缺口锁定" },
    });
  }
  expect(res.ok(), `研究锁定失败 HTTP ${res.status()} ${await res.text()}`).toBeTruthy();
  return res.json();
}

test("研究 R3 → 辩论 P3 → 三关 → 授权执行 → 持仓更新", async ({ page, request }) => {
  test.skip(!writeEnabled, "写库用例需要 INST_E2E_ALLOW_WRITE=1 且服务端库名为 svquant_test");
  test.setTimeout(300_000);

  const company = await pickCompany(request);
  const symbol = String(company.symbol);
  const beforeQty = await holdingQty(request, symbol);

  const created = await call(request, "POST", "/api/inst/cases", T.manager, {
    company_id: Number(company.id),
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
  await lockResearch(request, versionId);

  const locked = await call(request, "GET", `/api/inst/cases/${caseId}`, T.manager);
  expect(Number(locked.stage_no), "研究锁定后应进入 02→多空辩论").toBe(2);
  expect(locked.versions?.[0]?.locked_at, "研究版本应有 locked_at").toBeTruthy();

  await call(request, "POST", `/api/inst/cases/${caseId}/debate`, T.manager, {
    use_ai: false,
  });

  // 打开 v3 辩论工作台：进入第 4 步「议案」，填写意见并锁定 P3。
  await page.addInitScript((t) => sessionStorage.setItem("svquant_inst_token", t), T.manager);
  await page.goto(`${BASE}/inst/debate?key=${encodeURIComponent(`case:${caseId}`)}`, {
    waitUntil: "networkidle",
  });
  // 主区分段切换与右侧 Agent 面板双向同步。
  await expect(page.locator(".v3-side-switch button")).toHaveCount(2);
  await expect(page.locator(".v3-agent-pick")).toHaveCount(2);
  await page.locator(".v3-side-switch button").nth(1).click();
  await expect(page.getByText("空方 · 空头研究员 Agent", { exact: true })).toBeVisible();
  await expect(page.locator(".v3-agent-pick.on")).toContainText("空头研究员");
  const headline = await page.locator(".v3-claim .claim-t").first().innerText();
  expect(headline.length, "每条论点应是一句短论点").toBeLessThanOrEqual(50);
  await page.locator(".v3-stepper .v3-step").nth(3).click();
  const opinion = page.getByTestId("inst-investment-opinion");
  await opinion.fill("E2E 投资意见：关键假设成立、估值有安全边际才持有");
  // 目标权重按组合盯市净值与可用现金收敛：测试库是长期累积的真实数据，
  // 反复买入会把现金买光，固定 1% 会在若干轮后触发"现金不足"。
  const pf = await call(request, "GET", "/api/inst/portfolio", T.manager);
  const cashNow = Number(pf.cash || 0);
  const navNow = Number(pf.nav || 0);
  const affordable = navNow > 0 ? (cashNow * 0.5) / navNow : 0.01;
  const targetWeight = Math.max(0.001, Math.floor(Math.min(0.01, affordable) * 1000) / 1000);
  await page.getByTestId("inst-proposal-target").fill(targetWeight.toFixed(3));
  await page.getByTestId("inst-price-low").fill("1");
  await page.getByTestId("inst-price-high").fill("1000");
  await page.getByTestId("inst-proposal-create").click();
  await page.waitForURL(/\/inst\/approvals\?key=proposal(:|%3A)\d+/, { timeout: 120_000 });

  const proposalId = Number(
    decodeURIComponent(new URL(page.url()).searchParams.get("key") || "").split(":")[1],
  );
  expect(proposalId).toBeGreaterThan(0);

  // 锁定后：议案状态应为 partner_review，阶段 3。
  const submitted = await call(request, "GET", `/api/inst/proposals/${proposalId}`, T.manager);
  expect(submitted.status).toBe("partner_review");
  const caseAtApproval = await call(request, "GET", `/api/inst/cases/${caseId}`, T.manager);
  expect(Number(caseAtApproval.stage_no)).toBe(3);

  // 顺序固定：合伙人 → 风控 → Chairman。
  const partner = await call(
    request,
    "POST",
    `/api/inst/proposals/${proposalId}/partner`,
    T.partner,
    { decision: "approve", comment: "E2E 合伙人复核" },
  );
  expect(partner.status, "合伙人全部通过后进入风控").toBe("risk_precheck");
  const risk = await call(request, "POST", `/api/inst/proposals/${proposalId}/risk-check`, T.risk, {
    decision: "pass",
  });
  expect(risk.status, "风控应放行").toBe("chairman_review");
  await call(request, "POST", `/api/inst/proposals/${proposalId}/chairman`, T.chairman, {
    decision: "approve",
  });

  // AUTH 快照 → 执行成交。
  const authorized = await call(
    request,
    "POST",
    `/api/inst/proposals/${proposalId}/authorize`,
    T.chairman,
  );
  const authId = Number(authorized.authorizations[0].id);
  expect(authId).toBeGreaterThan(0);
  const executed = await call(
    request,
    "POST",
    `/api/inst/authorizations/${authId}/execute`,
    T.manager,
    { price: Number(company.ref_price) || 42 },
  );
  expect(Number(executed.order?.qty || 0)).toBeGreaterThan(0);

  const afterQty = await holdingQty(request, symbol);
  expect(afterQty).toBeGreaterThan(beforeQty);
  const caseAfter = await call(request, "GET", `/api/inst/cases/${caseId}`, T.manager);
  expect(Number(caseAfter.stage_no), "成交后进入投资管理").toBe(5);

  // 结果页展示三次锁定与最终持仓。
  await page.goto(
    `${BASE}/inst/pipeline/result?key=${encodeURIComponent(`case:${caseId}`)}`,
    { waitUntil: "networkidle" },
  );
  await expect(page.getByText("研究锁定", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("议案锁定", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("授权 AUTH", { exact: true })).toBeVisible();
  await expect(page.getByText(/股 · 权重/).first()).toBeVisible();
});
