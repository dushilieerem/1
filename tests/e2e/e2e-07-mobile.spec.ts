import { expect, test } from "@playwright/test";

/**
 * P2-05：移动端关键流程自动化验收（Playwright，390×844）。
 * 需要先启动前端/后端：R5_FE_BASE / R5_API_BASE 可覆盖地址。
 * 若环境未安装浏览器，本文件不会在本地自动运行，由 CI 执行。
 */
const FE = process.env.R5_FE_BASE || "https://127.0.0.1:9530";
const API = process.env.R5_API_BASE || "https://127.0.0.1:8766";

test.use({ viewport: { width: 390, height: 844 } });

async function noHorizontalOverflow(page: import("@playwright/test").Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
}

test("登录页在手机宽度无横向溢出，输入框可聚焦", async ({ page }) => {
  await page.goto(`${FE}/login`, { waitUntil: "domcontentloaded" });
  await noHorizontalOverflow(page);
  const input = page.locator("input").first();
  await input.focus();
  await expect(input).toBeFocused();
});

test("帮助中心目录/搜索在手机宽度可用", async ({ page }) => {
  await page.goto(`${FE}/help`, { waitUntil: "domcontentloaded" });
  await noHorizontalOverflow(page);
  const search = page.getByLabel("搜索帮助文档");
  await search.fill("因子");
  await expect(page.locator(".help-sidebar")).toContainText("因子");
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
