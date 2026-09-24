import { test, expect } from "@playwright/test";
import {
  FE, RUN_ID, USER_A, USER_B, USER_C, PW, ADMIN_USER, ADMIN_PW,
  api, registerUser, loginUser, reUp, blockStep, loginUi, sessionOf, noSecretLeak,
} from "./helpers/r5";

/**
 * E2E-01 认证与自选股（用户流程一：注册/登录/Token/退出/权限跳转 + 行情与自选股前段）
 * 关联用例：TC-AUTH-001/002/010、TC-MKT-004/008/009/013
 */

let tokenA = "";
const WL_NAME = `${RUN_ID}_wl`;

test.beforeAll(async ({ request }) => {
  tokenA = (await registerUser(request, USER_A, PW)).token;
  await registerUser(request, USER_B, PW);
});

test.afterAll(async ({ request }) => {
  // 业务数据清理（用户行由 backend/tests/r5_e2e_cleanup.py 统一清除）
  const res = await api(request, "GET", "/api/watchlists", { token: tokenA });
  for (const wl of res.json?.watchlists || res.json?.items || []) {
    if (String(wl.name || "").includes("R5_TEST")) {
      await api(request, "DELETE", `/api/watchlists/${wl.id}`, { token: tokenA });
    }
  }
});

test("注册新用户并自动建立会话（UI）", async ({ page }) => {
  await page.goto(FE + "/register");
  const form = page.locator('input[type="password"]').first().locator("xpath=ancestor::form[1]");
  await form.locator("input").first().fill(USER_C);
  await form.locator('input[type="password"]').fill(PW);
  await form.getByRole("button").click();
  await page.waitForURL((u) => !u.pathname.startsWith("/register"), { timeout: 20_000 });
  const sess = await sessionOf(page);
  expect(sess.token, "注册后应持有 token").toBeTruthy();
  expect(sess.user?.role, "注册用户角色应为 user").toBe("user");
  expect(sess.user?.username).toBe(USER_C);
});

test("登录失败提示与成功登录（UI）", async ({ page }) => {
  await page.goto(FE + "/login");
  const form = page.locator('input[type="password"]').first().locator("xpath=ancestor::form[1]");
  await form.locator("input").first().fill(USER_A);
  await form.locator('input[type="password"]').fill("WrongPass!");
  await form.getByRole("button").click();
  await expect(form.locator(".text-red-600")).toBeVisible({ timeout: 10_000 });

  await form.locator('input[type="password"]').fill(PW);
  await form.getByRole("button").click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20_000 });
  const sess = await sessionOf(page);
  expect(sess.token).toBeTruthy();
  expect(sess.user?.username).toBe(USER_A);
});

test("退出登录后受保护路由跳转登录页（UI 权限跳转）", async ({ page }) => {
  await loginUi(page, USER_A, PW);
  await page.getByRole("button", { name: new RegExp(USER_A) }).click();
  await page.getByText("退出登录").first().click();
  await expect
    .poll(async () => (await sessionOf(page)).token, { timeout: 10_000 })
    .toBeNull();
  await page.goto(FE + "/data/watchlist");
  await page.waitForURL(/\/login/, { timeout: 15_000 });
});

test("创建自选组合并加入标的（UI，RE 依赖标的搜索）", async ({ page }, testInfo) => {
  if (!(await reUp(page.request))) await blockStep(testInfo, "RE 不可达：标的搜索/行情链路 BLOCKED");
  await loginUi(page, USER_A, PW);
  await page.goto(FE + "/data/watchlist");
  await page.getByText("新建组合").first().click();
  const dialog = page.locator("div").filter({ hasText: "新建自选组合" }).locator("visible=true").last();
  await dialog.locator('input[placeholder="组合名称"]').fill(WL_NAME);
  await dialog.getByRole("button", { name: /确定|创建|保存/ }).click();
  await expect(page.getByRole("button", { name: new RegExp(WL_NAME) }).first()).toBeVisible({ timeout: 15_000 });

  // 搜索标的并加入（走 /api → 后端 → RE）
  await page.getByRole("button", { name: "浏览选股" }).click();
  await page.locator('input[placeholder="搜索代码 / 名称…"]').first().fill("000001");
  await page.waitForTimeout(1_500);
  const addBtn = page.getByRole("button", { name: "加入", exact: true }).first();
  await addBtn.click({ timeout: 15_000 });

  const list = await api(page.request, "GET", "/api/watchlists", { token: tokenA });
  const names = JSON.stringify(list.json);
  expect(list.status).toBe(200);
  expect(names).toContain(WL_NAME);
});

test("行情日线经网关可用（RE 依赖，API）", async ({ request }, testInfo) => {
  if (!(await reUp(request))) await blockStep(testInfo, "RE 不可达：行情日线 BLOCKED");
  const r = await api(request, "GET", "/api/market-data/symbols");
  expect(r.status).toBe(200);
  expect(noSecretLeak(r.json)).toBeTruthy();
});

test("自选股跨用户访问被拒（IDOR 回归）", async ({ request }) => {
  const created = await api(request, "POST", "/api/watchlists", { token: tokenA, body: { name: `${RUN_ID}_idor` } });
  const wlId = created.json?.watchlist?.id;
  expect(created.status).toBe(200);
  const tokenB = (await loginUser(request, USER_B, PW)).token;
  for (const [method, path] of [
    ["GET", `/api/watchlists/${wlId}/symbols`],
    ["PUT", `/api/watchlists/${wlId}`],
    ["DELETE", `/api/watchlists/${wlId}`],
  ] as const) {
    const r = await api(request, method, path, { token: tokenB, body: method === "PUT" ? { name: "evil" } : undefined });
    expect([403, 404], `${method} ${path} 应拒绝`).toContain(r.status);
  }
});

test("管理接口权限矩阵（审计日志 admin/user/anonymous）", async ({ request }) => {
  const tokenAdmin = (await loginUser(request, ADMIN_USER, ADMIN_PW)).token;
  const rAdmin = await api(request, "GET", "/api/admin/logs?limit=1", { token: tokenAdmin });
  expect(rAdmin.status).toBe(200);
  expect(noSecretLeak(rAdmin.json)).toBeTruthy();
  const rUser = await api(request, "GET", "/api/admin/logs?limit=1", { token: tokenA });
  expect(rUser.status).toBe(403);
  const rAnon = await api(request, "GET", "/api/admin/logs?limit=1");
  expect(rAnon.status).toBe(401);
});
