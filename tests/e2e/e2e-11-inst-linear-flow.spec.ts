import { expect, test, type APIRequestContext } from "@playwright/test";

import { evaluateWriteGuard } from "./helpers/write-guard.mjs";

/**
 * 线性流程 B 全链路：辩论完成自动创建议案 → 合伙人 → Chairman → 风控
 * → 审批最后一关自动授权 + 模拟成交 → 投资组合持仓更新。
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
  for (const role of ["manager", "partner", "chairman", "risk"]) {
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

async function holdingQty(request: APIRequestContext, symbol: string): Promise<number> {
  const portfolio = await call(request, "GET", "/api/inst/portfolio", T.manager);
  return (portfolio.positions || [])
    .filter((p: any) => p.symbol === symbol)
    .reduce((sum: number, p: any) => sum + Number(p.qty || 0), 0);
}

test("辩论后补议案 → 审批 → 自动授权成交 → 持仓更新", async ({ page, request }) => {
  test.skip(!writeEnabled, "写库用例需要 INST_E2E_ALLOW_WRITE=1 且服务端库名为 svquant_test");
  test.setTimeout(300_000);

  // 选一只尚未持有、且行业未过度集中的标的：重复运行不会把自己持有的票越买越集中。
  const portfolioBefore = await call(request, "GET", "/api/inst/portfolio", T.manager);
  const positionsBefore = (portfolioBefore.positions || []).filter((p: any) => Number(p.qty) > 0);
  const held = new Set(positionsBefore.map((p: any) => String(p.symbol)));
  const crowded = new Set(
    positionsBefore
      .filter((p: any) => Number(p.weight || 0) > 0.2 && p.industry)
      .map((p: any) => String(p.industry)),
  );
  const companies = await call(request, "GET", "/api/inst/companies?limit=200", T.manager);
  const company = (companies.items || []).find(
    (c: any) =>
      c.market === "CN" &&
      Number(c.ref_price) > 0 &&
      !held.has(String(c.symbol)) &&
      !crowded.has(String(c.industry || "")),
  );
  expect(company, "找不到可用于买入流程的未持仓标的").toBeTruthy();
  const symbol = String(company.symbol);
  const beforeQty = await holdingQty(request, symbol);

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
  await call(request, "POST", `/api/inst/research/${versionId}/review`, T.partner, {
    decision: "approve",
    comment: "E2E 线性流程",
  });
  await call(request, "POST", `/api/inst/cases/${caseId}/debate`, T.manager, {
    use_ai: false,
  });

  // 打开辩论页：填写投资意见并生成议案（不再自动建案跳转）。
  await page.addInitScript((t) => sessionStorage.setItem("svquant_inst_token", t), T.manager);
  await page.goto(`${BASE}/inst/debate?case=${caseId}`, { waitUntil: "networkidle" });
  await page.getByTestId("inst-investment-opinion").fill("E2E 投资意见：关键假设与退出条件");
  // 价格区间必须覆盖现价，否则风控会按「现价超出批准区间」否决。
  await page.getByTestId("inst-price-low").fill("1");
  await page.getByTestId("inst-price-high").fill("1000");
  await page.getByTestId("inst-proposal-create").click();
  await page.waitForURL(/\/inst\/approvals\?proposal=\d+/, { timeout: 60_000 });
  const proposalId = Number(new URL(page.url()).searchParams.get("proposal"));
  expect(proposalId).toBeGreaterThan(0);

  // 顺序固定：合伙人 → 风控 → Chairman。
  await call(request, "POST", `/api/inst/proposals/${proposalId}/partner`, T.partner, {
    decision: "approve",
  });
  const risk = await call(request, "POST", `/api/inst/proposals/${proposalId}/risk-check`, T.risk, {});
  expect(risk.status, "风控应放行").toBe("chairman_review");
  await call(request, "POST", `/api/inst/proposals/${proposalId}/chairman`, T.chairman, {
    decision: "approve",
  });

  // 方案 B：授权 + 模拟成交。
  const executed = await call(
    request,
    "POST",
    `/api/inst/proposals/${proposalId}/approve-and-execute`,
    T.chairman,
    { price: Number(company.ref_price) || 42 },
  );
  expect(executed.proposal?.status).toBe("executed");
  expect(executed.execution?.order?.side).toBe("buy");
  expect(executed.authorization_id).toBeGreaterThan(0);

  const afterQty = await holdingQty(request, symbol);
  expect(afterQty).toBeGreaterThan(beforeQty);

  // 旧执行入口重定向，侧栏不再出现交易执行。
  await page.goto(`${BASE}/inst/execution`, { waitUntil: "networkidle" });
  await expect(page).toHaveURL(/\/inst\/portfolio/);
  await expect(page.getByRole("link", { name: "交易执行" })).toHaveCount(0);
});
