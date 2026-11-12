import { expect, test, type APIRequestContext } from "@playwright/test";

import { evaluateWriteGuard } from "./helpers/write-guard.mjs";

/**
 * v3 研究定稿门禁 UI：门禁预览、低置信逐维复核、正常锁定或显式带缺口锁定。
 * 写库用例：INST_E2E_ALLOW_WRITE=1，且服务端 guard 必须是 svquant_test。
 */
const BASE = process.env.INST_BASE || "http://127.0.0.1:9533";
const API = process.env.INST_API || "http://127.0.0.1:8771";
const PW = process.env.INST_PASSWORD || "inst123456";
const ALLOW_WRITE = process.env.INST_E2E_ALLOW_WRITE === "1";
let writeEnabled = false;

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
  if (!ALLOW_WRITE) return;
  const token = await login(request, "inst_manager");
  const res = await request.get(`${API}/api/inst/_e2e/guard`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = res.ok() ? await res.json() : { error: `HTTP ${res.status}` };
  const guard = evaluateWriteGuard({ allowWrite: true, guardResponse: data });
  if (guard.fatal) throw new Error(guard.fatal);
  writeEnabled = guard.enabled;
});

test("研究定稿：门禁预览 → 低置信复核 → 锁定 R3", async ({ page, request }) => {
  test.skip(!writeEnabled, "写库用例需要 INST_E2E_ALLOW_WRITE=1 且服务端库名为 svquant_test");
  test.setTimeout(300_000);

  const token = await login(request, "inst_manager");
  const companies = await call(request, "GET", "/api/inst/companies?limit=200", token);
  const company = (companies.items || []).find(
    (c: any) =>
      c.market === "CN" &&
      Number(c.ref_price) >= 5 &&
      c.data_status === "real" &&
      c.up_down_status === "非涨跌停" &&
      !c.is_st &&
      !c.is_suspended,
  );
  expect(company, "找不到可用于研究定稿测试的标的").toBeTruthy();

  const created = await call(request, "POST", "/api/inst/cases", token, {
    company_id: Number(company.id),
  });
  const caseId = Number(created.id);
  const research = await call(
    request,
    "POST",
    `/api/inst/cases/${caseId}/research`,
    token,
    { mode: "full" },
  );
  const versionId = Number(research.versions[0].id);
  const gate = await call(request, "GET", `/api/inst/research/${versionId}/gate`, token);
  expect(["pass", "warn", "block"]).toContain(gate.status);
  expect(gate.checks.map((x: any) => x.key)).toEqual(
    expect.arrayContaining(["six_dim_complete", "low_confidence", "data_gate", "evidence", "hash"]),
  );

  await page.addInitScript((t) => sessionStorage.setItem("svquant_inst_token", t), token);
  await page.goto(`${BASE}/inst/research?key=${encodeURIComponent(`case:${caseId}`)}`, {
    waitUntil: "networkidle",
  });
  // 右侧 Agent 面板：六位研究员可切换，主区同步切换当前维度。
  await page.locator(".v3-stepper .v3-step").nth(1).click();
  await expect(page.locator(".v3-agent-pick")).toHaveCount(6);
  await page.locator(".v3-agent-pick").filter({ hasText: "财务质量" }).click();
  await expect(page.locator(".v3-dim-btn.on")).toHaveText(/财务质量/);
  await page.locator(".v3-stepper .v3-step").nth(3).click();
  await expect(page.getByText("研究定稿", { exact: true }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("六维 6/6", { exact: true })).toBeVisible();
  await expect(page.getByText("低置信项已处理", { exact: true })).toBeVisible();
  await expect(page.getByText("数据门禁", { exact: true })).toBeVisible();
  await expect(page.getByText("版本校验码", { exact: true })).toBeVisible();

  // 有低置信项时先逐维复核；复核说明写入审计。
  for (let i = 0; i < 6; i += 1) {
    const review = page.getByRole("button", { name: /复核通过 ·/ }).first();
    if (!(await review.count())) break;
    await page.locator(".v3-field input").fill(`E2E 复核说明 ${i + 1}`);
    await review.click();
    await expect(review).toHaveCount(0, { timeout: 30_000 }).catch(() => undefined);
  }

  // 门禁仍阻断时走显式带缺口锁定；否则正常锁定。
  const gapCheckbox = page.locator('input[type="checkbox"]');
  if (await gapCheckbox.count()) {
    await gapCheckbox.check();
    await page.getByTestId("inst-research-lock-gaps").click();
  } else {
    await page.getByTestId("inst-research-lock").click();
  }
  await expect(page.getByText("已锁定", { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("link", { name: /移交多空辩论/ })).toBeVisible();

  const detail = await call(request, "GET", `/api/inst/cases/${caseId}`, token);
  expect(Number(detail.stage_no)).toBe(2);
  expect(detail.versions?.[0]?.locked_at).toBeTruthy();
});
