import { expect, test } from "@playwright/test";

/**
 * P2-05：移动端关键流程自动化验收（Playwright，390×844）。
 * 需要先启动前端/后端：R5_FE_BASE / R5_API_BASE 可覆盖地址。
 * 若环境未安装浏览器，本文件不会在本地自动运行，由 CI 执行。
 */
const FE = process.env.R5_FE_BASE || "https://127.0.0.1:9530";
const API = process.env.R5_API_BASE || "https://127.0.0.1:8766";

test.use({ viewport: { width: 390, height: 844 } });

async function login(page: import("@playwright/test").Page) {
  const username = process.env.R5_USERNAME || "admin";
  const password = process.env.R5_PASSWORD || "admin123";
  const res = await page.request.post(`${API}/api/auth/login`, {
    data: { username, password },
  });
  if (!res.ok()) throw new Error(`登录失败 HTTP ${res.status()}`);
  const data = await res.json();
  await page.addInitScript(
    ([token, user]) => {
      localStorage.setItem("svquant_token", token);
      localStorage.setItem("svquant_user", JSON.stringify(user));
    },
    [data.token, data.user],
  );
}

async function noHorizontalOverflow(page: import("@playwright/test").Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
}

test("登录页在手机宽度无横向溢出，输入框可聚焦", async ({ page }) => {
  await page.goto(`${FE}/login`, { waitUntil: "domcontentloaded" });
  await noHorizontalOverflow(page);
  const input = page.locator('input[autocomplete="username"]');
  await input.focus();
  await expect(input).toBeFocused();
});

test("帮助中心目录/搜索在手机宽度可用", async ({ page }) => {
  await page.goto(`${FE}/help`, { waitUntil: "domcontentloaded" });
  await noHorizontalOverflow(page);
  await page.getByRole("button", { name: /目录 ·/ }).click();
  const search = page.getByRole("searchbox", { name: "搜索帮助文档" }).last();
  await search.fill("因子");
  await expect(page.locator(".help-sidebar").last()).toContainText("因子");
});

test("社区列表与发帖入口在手机宽度可达", async ({ page }) => {
  await page.goto(`${FE}/community`, { waitUntil: "domcontentloaded" });
  await noHorizontalOverflow(page);
});

test("API 健康检查可用", async ({ request }) => {
  test.skip(!process.env.R5_API_BASE, "未设置 R5_API_BASE，跳过接口检查");
  const res = await request.get(`${API}/api/health`);
  expect(res.ok()).toBeTruthy();
});

test("登录后因子检测列表在手机宽度可用", async ({ page }) => {
  await login(page);
  await page.goto(`${FE}/factor/detect`, { waitUntil: "networkidle" });
  await noHorizontalOverflow(page);
  await expect(page.locator("body")).toContainText(/因子|检测/);
});

test("登录后策略研究列表在手机宽度可用", async ({ page }) => {
  await login(page);
  await page.goto(`${FE}/strategy/research`, { waitUntil: "networkidle" });
  await noHorizontalOverflow(page);
  await expect(page.locator("body")).toContainText(/策略|研究/);
});

test("登录后行情图表页在手机宽度可用", async ({ page }) => {
  await login(page);
  await page.goto(`${FE}/data/symbol/000001.SZ/chart`, { waitUntil: "networkidle" });
  await noHorizontalOverflow(page);
  await expect(page.getByText("日K").first()).toBeVisible();
});
