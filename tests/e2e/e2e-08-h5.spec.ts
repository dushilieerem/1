import { expect, test } from "@playwright/test";

/**
 * A4：手机 H5 自身验收（Playwright，390×844）。
 * 独立于主站移动视口用例（e2e-07），直接跑 frontend/invest。
 * 启动方式：`cd frontend/invest && npm run dev`（9540）或 `npm run preview`（9541）。
 * 地址可用 R5_H5_BASE 覆盖；后端经 H5 的 /api 代理访问。
 */
const H5 = process.env.R5_H5_BASE || "http://127.0.0.1:9540";
const API = process.env.R5_API_BASE || "http://127.0.0.1:8766";
const RUN_ID = process.env.R5_RUN_ID || `R5_TEST_${Math.floor(Date.now() / 1000)}`;
const EPOCH = (RUN_ID.match(/\d{5,}/) || [String(Date.now())])[0].slice(-8);
const USER = `R5_TEST_h5_${EPOCH}`;
const PW = "R5Test123!";

test.use({ viewport: { width: 390, height: 844 } });

let token = "";

async function noHorizontalOverflow(page: import("@playwright/test").Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
}

test.beforeAll(async ({ request }) => {
  let res = await request.post(`${API}/api/auth/register`, {
    data: { username: USER, password: PW },
  });
  if (res.status() === 400) {
    res = await request.post(`${API}/api/auth/login`, { data: { username: USER, password: PW } });
  }
  expect(res.ok(), `准备测试账号失败 HTTP ${res.status()}`).toBeTruthy();
  token = (await res.json()).token;
  expect(token).toBeTruthy();
});

test.afterAll(async ({ request }) => {
  if (!token) return;
  await request
    .post(`${API}/api/auth/account/delete`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { password: PW, confirm: USER },
    })
    .catch(() => {});
});

async function loginByToken(page: import("@playwright/test").Page) {
  await page.addInitScript((t) => {
    sessionStorage.setItem("svq_invest_token", t);
  }, token);
}

test("登录页在手机宽度可用，找回密码入口可见", async ({ page }) => {
  await page.goto(`${H5}/login`, { waitUntil: "domcontentloaded" });
  await noHorizontalOverflow(page);
  await expect(page.locator('input[autocomplete="username"]')).toBeVisible();
  await expect(page.locator('input[type="password"]')).toBeVisible();
  await expect(page.getByRole("link", { name: "忘记密码" })).toBeVisible();
});

test("登录后首页渲染且保留收盘/非实时标识", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".home-page")).toBeVisible({ timeout: 30_000 });
  await noHorizontalOverflow(page);
  await expect(page.locator("body")).toContainText(/收盘|非实时/);
});

test("「我的」页有数据口径与账号注销入口", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/me`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("数据日期", { exact: false })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("注销 SVQuant 账号")).toBeVisible();
  // 只验证入口存在，不在 E2E 里提交注销
  await noHorizontalOverflow(page);
});

test("弱网下首页仍能给出内容或明确错误态", async ({ page }) => {
  await loginByToken(page);
  // 只给接口加延迟：dev server 的模块加载不走弱网，避免测成“包大不大”
  await page.route("**/api/invest/**", async (route) => {
    await new Promise((r) => setTimeout(r, 2500));
    await route.continue();
  });
  await page.goto(`${H5}/`, { waitUntil: "domcontentloaded" });
  await expect(page.locator("body")).not.toBeEmpty();
  await expect(page.locator(".home-page, .error-state, .empty-state")).toBeVisible({
    timeout: 45_000,
  });
});

test("基础无障碍：主要按钮/链接有可访问名称", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".home-page")).toBeVisible({ timeout: 30_000 });
  const unnamed = await page.evaluate(() => {
    const nodes = Array.from(document.querySelectorAll("button, a"));
    return nodes.filter((el) => {
      const text = (el.textContent || "").trim();
      const aria = el.getAttribute("aria-label") || "";
      return !text && !aria;
    }).length;
  });
  expect(unnamed).toBe(0);
});

test("社区列表可打开且无横向溢出", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/community`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "社区" })).toBeVisible({ timeout: 20_000 });
  await noHorizontalOverflow(page);
  await expect(page.locator(".post-list, .empty-state")).toBeVisible({ timeout: 20_000 });
});

test("未登录访问社区会跳转登录页", async ({ page }) => {
  await page.goto(`${H5}/community`, { waitUntil: "domcontentloaded" });
  await page.waitForURL(/\/login/, { timeout: 20_000 });
  await expect(page.locator('input[autocomplete="username"]')).toBeVisible();
});

test("登录后可打开帖子详情（有帖子时）", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/community`, { waitUntil: "domcontentloaded" });
  const first = page.locator(".post-row").first();
  if (await first.count()) {
    await first.click();
    await expect(page.getByText(/评论/)).toBeVisible({ timeout: 20_000 });
    await noHorizontalOverflow(page);
  }
});
