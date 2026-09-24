import { test, expect } from "@playwright/test";
import {
  FE, RUN_ID, USER_A, PW,
  api, registerUser, reUp, blockStep, loginUi, noSecretLeak,
} from "./helpers/r5";

/**
 * E2E-02 因子研究闭环（用户流程三：研究人员流程）
 * 关联用例：TC-FACTOR-001/002/005/014/021、TC-RE-002
 */

let tokenA = "";
const LIB_NAME = `${RUN_ID}_lib`;
const FACTOR_NAME = `r5f${RUN_ID.replace(/\D/g, "").slice(-8)}`;

test.beforeAll(async ({ request }) => {
  tokenA = (await registerUser(request, USER_A, PW)).token;
});

test.afterAll(async ({ request }) => {
  const res = await api(request, "GET", "/api/factor/libraries", { token: tokenA });
  for (const lib of res.json?.libraries || res.json?.items || []) {
    if (String(lib.name || "").includes("R5_TEST")) {
      await api(request, "DELETE", `/api/factor/libraries/${lib.id}`, { token: tokenA });
    }
  }
});

test("创建用户因子库（UI）", async ({ page }) => {
  await loginUi(page, USER_A, PW);
  await page.goto(FE + "/factor/library");
  await page.getByRole("button", { name: "新增因子库" }).click();
  const modal = page.locator(".fixed.inset-0").last();
  await modal.locator('input[placeholder="例如 A / 我的研究库"]').fill(LIB_NAME);
  await modal.getByRole("button", { name: /确定|创建|保存/ }).first().click();
  await expect(page.getByText(LIB_NAME).first()).toBeVisible({ timeout: 15_000 });

  const list = await api(page.request, "GET", "/api/factor/libraries", { token: tokenA });
  expect(list.status).toBe(200);
  expect(JSON.stringify(list.json)).toContain(LIB_NAME);
});

test("创建自定义因子（UI）", async ({ page }) => {
  await loginUi(page, USER_A, PW);
  await page.goto(FE + "/factor/library");
  await page.getByRole("button", { name: "新建因子" }).click();
  const modal = page.locator(".fixed.inset-0").last();
  await modal.locator("input").first().fill(FACTOR_NAME);
  await modal.locator("label", { hasText: "中文解释" }).locator("input").fill("R5 E2E 测试因子");
  await modal.locator("label", { hasText: "分类" }).locator("select").selectOption({ index: 1 });
  await modal.locator("label", { hasText: "所属用户因子库" }).locator("select").selectOption({ label: LIB_NAME });
  const expr = modal.locator("textarea").first();
  if (await expr.count()) await expr.fill("close.pct_change(5)");
  await modal.getByRole("button", { name: /创建|保存|确定/ }).click();
  await expect(page.getByText(FACTOR_NAME).first()).toBeVisible({ timeout: 15_000 });
});

test("非法因子输入被拒绝（UI→API 契约）", async ({ request }) => {
  const r = await api(request, "POST", "/api/factor/libraries", { token: tokenA, body: { name: `${RUN_ID}_invalid_lib` } });
  const libId = r.json?.library?.id;
  const bad = await api(request, "POST", `/api/factor/libraries/${libId}/factors`, {
    token: tokenA,
    body: { name: "", body: "" },
  });
  expect(bad.status).toBe(400);
});

test("因子目录经 RE 获取（re-catalog，RE 依赖）", async ({ request }, testInfo) => {
  if (!(await reUp(request))) await blockStep(testInfo, "RE 不可达：re-catalog BLOCKED");
  const r = await api(request, "GET", "/api/factor/re-catalog", { token: tokenA });
  expect(r.status).toBe(200);
  expect(r.json && typeof r.json === "object").toBeTruthy();
});

test("行情符号代理可用（RE 依赖）", async ({ request }, testInfo) => {
  if (!(await reUp(request))) await blockStep(testInfo, "RE 不可达：行情符号 BLOCKED");
  const r = await api(request, "GET", "/api/market-data/symbols", { token: tokenA });
  expect(r.status).toBe(200);
  expect(noSecretLeak(r.json)).toBeTruthy();
});

test("因子面板页加载（UI，登录态）", async ({ page }) => {
  await loginUi(page, USER_A, PW);
  await page.goto(FE + "/factor/dashboard");
  await expect(page.locator("body")).toContainText(/因子|面板/, { timeout: 20_000 });
});
