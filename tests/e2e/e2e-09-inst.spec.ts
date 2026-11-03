import { expect, test, type APIRequestContext } from "@playwright/test";

import { evaluateWriteGuard } from "./helpers/write-guard.mjs";

/**
 * 主观机构端 E2E 冒烟：登录、侧栏顺序、九个工作区可达、退出流程。
 * 默认连本地 Vite 9533 + 后端 8771；可用 INST_BASE / INST_API 覆盖。
 *
 * 默认只跑只读用例。退出流程会建持仓/研究案/退出案/议案，属于写库用例：
 *   INST_E2E_ALLOW_WRITE=1 npx playwright test e2e-09-inst.spec.ts
 * 写库前必须请求服务端 GET /api/inst/_e2e/guard，只有服务端返回的真实库名含
 * _test/_e2e 才放行；生产库 svquant、端点不可达或返回缺失都直接失败。
 * 可选 INST_E2E_EXPECT_DB 精确比对服务端返回的库名。
 */
const ALLOW_WRITE = process.env.INST_E2E_ALLOW_WRITE === "1";
let writeGuard = evaluateWriteGuard({ allowWrite: false });
const BASE = process.env.INST_BASE || "http://127.0.0.1:9533";
const API = process.env.INST_API || "http://127.0.0.1:8771";
const USER = process.env.INST_USER || "inst_manager";
const PW = process.env.INST_PASSWORD || "inst123456";

const ROLES = ["manager", "partner", "chairman", "risk", "execution", "monitoring"] as const;
type Role = (typeof ROLES)[number];

test.use({ viewport: { width: 1440, height: 900 } });

let token = "";
const tokens: Partial<Record<Role, string>> = {};

async function loginApi(request: APIRequestContext, username: string): Promise<string> {
  const res = await request.post(`${API}/api/inst/auth/login`, {
    data: { username, password: PW },
  });
  expect(res.ok(), `机构登录失败 ${username} HTTP ${res.status()}`).toBeTruthy();
  const data = await res.json();
  expect(data.token).toBeTruthy();
  return data.token;
}

/** 读服务端真实库名；不可达/非 200/返回缺失都交给 guard 判 fatal。 */
async function resolveWriteGuard(request: APIRequestContext) {
  let guardResponse: any = null;
  try {
    const res = await request.get(`${API}/api/inst/_e2e/guard`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    guardResponse = res.ok() ? await res.json() : { error: `HTTP ${res.status()}` };
  } catch {
    guardResponse = null;
  }
  return evaluateWriteGuard({
    allowWrite: true,
    guardResponse,
    expectDb: process.env.INST_E2E_EXPECT_DB,
  });
}

async function call(
  request: APIRequestContext,
  method: "GET" | "POST",
  path: string,
  auth: string,
  data?: Record<string, unknown>,
): Promise<any> {
  const res = await request.fetch(`${API}${path}`, {
    method,
    headers: { Authorization: `Bearer ${auth}` },
    data,
  });
  const text = await res.text();
  if (!res.ok()) throw new Error(`${method} ${path} → ${res.status()} ${text.slice(0, 300)}`);
  return text ? JSON.parse(text) : {};
}

test.beforeAll(async ({ request }) => {
  token = await loginApi(request, USER);
  tokens.manager = token;
  await Promise.all(
    ROLES.filter((r) => r !== "manager").map(async (role) => {
      tokens[role] = await loginApi(request, `inst_${role}`);
    }),
  );
  if (ALLOW_WRITE) {
    writeGuard = await resolveWriteGuard(request);
    if (writeGuard.fatal) throw new Error(writeGuard.fatal);
  }
});

async function login(page: import("@playwright/test").Page) {
  await page.addInitScript((t) => sessionStorage.setItem("svquant_inst_token", t), token);
}

test("机构端侧栏名称与顺序", async ({ page }) => {
  await login(page);
  await page.goto(`${BASE}/inst/overview`, { waitUntil: "networkidle" });
  await expect(page.locator("aside nav a")).toHaveText([
    "投资总览",
    "机会发现",
    "公司研究",
    "投资辩论室",
    "投委会审批",
    "交易执行",
    "投资组合",
    "投后管理",
    "Agent能力",
  ]);
  await expect(page.getByText("以企业为起点，以证据做决策")).toBeVisible();
});

test("研究、审批、执行、投后、Agent能力页面可达", async ({ page }) => {
  await login(page);
  for (const [path, text] of [
    ["/inst/ideas", "量化策略推送"],
    ["/inst/research", "公司研究"],
    ["/inst/approvals", "投委会审批"],
    ["/inst/execution", "交易执行"],
    ["/inst/monitor", "投后管理"],
    ["/inst/about", "Agent能力"],
  ]) {
    await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
    await expect(page.getByText(text, { exact: false }).first()).toBeVisible({ timeout: 20_000 });
  }
});

test("机构端无横向溢出", async ({ page }) => {
  await login(page);
  await page.goto(`${BASE}/inst/overview`, { waitUntil: "networkidle" });
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});

/** 保证演示机构有一笔持仓；没有则用一次小额买入走完整链路。 */
async function ensureHolding(request: APIRequestContext): Promise<number> {
  const portfolio = await call(request, "GET", "/api/inst/portfolio", tokens.manager!);
  const held = (portfolio.positions || []).find(
    (p: any) => Number(p.qty) > 0 && p.company_id,
  );
  if (held) return Number(held.company_id);

  const companies = await call(request, "GET", "/api/inst/companies?q=600519", tokens.manager!);
  const company = (companies.items || []).find((c: any) => String(c.symbol).startsWith("600519"));
  expect(company, "演示库缺少 600519，无法准备持仓").toBeTruthy();
  // 用真实参考价成交，避免在演示组合里留下不真实的成本价。
  const price = Number(company.ref_price) || 100;

  const created = await call(request, "POST", "/api/inst/cases", tokens.manager!, {
    company_id: Number(company.id),
  });
  const research = await call(
    request,
    "POST",
    `/api/inst/cases/${created.id}/research`,
    tokens.manager!,
    { mode: "valuation" },
  );
  const versionId = Number(research.versions[0].id);
  await call(request, "POST", `/api/inst/research/${versionId}/review`, tokens.partner!, {
    decision: "approve",
    comment: "E2E 准备持仓",
  });
  await call(request, "POST", `/api/inst/cases/${created.id}/debate`, tokens.manager!, {
    use_ai: false,
  });
  const proposal = await call(
    request,
    "POST",
    `/api/inst/cases/${created.id}/proposals`,
    tokens.manager!,
    { direction: "buy", target_weight: 0.02 },
  );
  await call(request, "POST", `/api/inst/proposals/${proposal.id}/partner`, tokens.partner!, {
    decision: "approve",
  });
  await call(request, "POST", `/api/inst/proposals/${proposal.id}/chairman`, tokens.chairman!, {
    decision: "approve",
  });
  await call(request, "POST", `/api/inst/proposals/${proposal.id}/risk-check`, tokens.risk!, {});
  const authorized = await call(
    request,
    "POST",
    `/api/inst/proposals/${proposal.id}/authorize`,
    tokens.chairman!,
  );
  const authId = Number(authorized.authorizations[0].id);
  await call(request, "POST", `/api/inst/authorizations/${authId}/execute`, tokens.execution!, {
    price,
  });
  return Number(company.id);
}

/** 建退出研究案并推进到「可创建议案」：研究 → 审核 → 辩论。 */
async function prepareExitCase(
  request: APIRequestContext,
): Promise<{ exitId: number; caseId: number }> {
  const companyId = await ensureHolding(request);
  const exitCase = await call(request, "POST", "/api/inst/monitor/exits", tokens.manager!, {
    company_id: companyId,
    reason_type: "thesis_invalid",
    memo: "E2E 退出流程",
  });
  const caseId = Number(exitCase.case_id);
  const research = await call(
    request,
    "POST",
    `/api/inst/cases/${caseId}/research`,
    tokens.manager!,
    { mode: "valuation" },
  );
  const versionId = Number(research.versions[0].id);
  await call(request, "POST", `/api/inst/research/${versionId}/review`, tokens.partner!, {
    decision: "approve",
    comment: "E2E 退出研究",
  });
  await call(request, "POST", `/api/inst/cases/${caseId}/debate`, tokens.manager!, {
    use_ai: false,
  });
  return { exitId: Number(exitCase.id), caseId };
}

test("退出流程：投后回链 → 辩论默认 exit/0 → 创建议案", async ({ page, request }) => {
  test.skip(
    !writeGuard.enabled,
    "写库用例默认关闭：需 INST_E2E_ALLOW_WRITE=1，且服务端 /api/inst/_e2e/guard 确认库名含 _test/_e2e（生产 svquant 永远拒绝）",
  );
  test.setTimeout(300_000);
  const { exitId, caseId } = await prepareExitCase(request);

  // 后端硬校验：退出案不能建买入议案。
  const buyAttempt = await request.fetch(`${API}/api/inst/cases/${caseId}/proposals`, {
    method: "POST",
    headers: { Authorization: `Bearer ${tokens.manager}` },
    data: { direction: "buy", target_weight: 0.05 },
  });
  expect(buyAttempt.status(), "退出案建买入议案应被拒绝").toBe(400);

  await login(page);
  await page.goto(`${BASE}/inst/monitor`, { waitUntil: "networkidle" });
  const exitCard = page
    .locator("li")
    .filter({ hasText: new RegExp(`EX-${exitId}(?!\\d)`) });
  await expect(exitCard).toBeVisible({ timeout: 20_000 });
  await expect(exitCard).toContainText("论点失效");
  const researchLink = exitCard.getByRole("link", { name: new RegExp(`退出研究案\\s*#${caseId}`) });
  await expect(researchLink).toBeVisible();

  // 辩论页：退出案默认 exit + 目标仓位 0，文案明确为退出议案。
  await page.goto(`${BASE}/inst/debate?case=${caseId}`, { waitUntil: "networkidle" });
  await expect(page.getByText("这是退出研究案", { exact: false })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByTestId("inst-proposal-target")).toHaveValue("0");
  const createBtn = page.getByTestId("inst-proposal-create");
  await expect(createBtn).toHaveText("创建退出议案");
  // 目标仓位 0 会弹清仓确认。
  page.once("dialog", (dialog) => dialog.accept());
  await createBtn.click();
  await page.waitForURL(/\/inst\/approvals\?proposal=\d+/, { timeout: 30_000 });

  const proposalId = Number(new URL(page.url()).searchParams.get("proposal"));
  expect(proposalId).toBeGreaterThan(0);
  const detail = await call(request, "GET", `/api/inst/proposals/${proposalId}`, tokens.manager!);
  expect(detail.direction).toBe("exit");
  expect(Number(detail.target_weight)).toBe(0);
  expect(detail.exit_case?.id).toBe(exitId);
  expect(detail.exit_case?.status).toBe("submitted");
  await expect(page.getByText(new RegExp(`退出案 EX-${exitId}(?!\\d)`))).toBeVisible({ timeout: 20_000 });

  // 投后列表回链议案，状态与议案一致。
  await page.goto(`${BASE}/inst/monitor`, { waitUntil: "networkidle" });
  const proposalLink = page
    .locator("li")
    .filter({ hasText: new RegExp(`EX-${exitId}(?!\\d)`) })
    .getByRole("link", { name: new RegExp(`退出议案\\s*#${proposalId}`) });
  await expect(proposalLink).toBeVisible();
});
