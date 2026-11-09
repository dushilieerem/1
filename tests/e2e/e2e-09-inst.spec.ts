import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * 主观机构端 v3 冒烟：登录、三组导航、八个入口、结果页、旧入口重定向、窄屏。
 * 默认连本地 Vite 9533 + 后端 8771；可用 INST_BASE / INST_API 覆盖。
 * 本文件只读，不写库。
 */
const BASE = process.env.INST_BASE || "http://127.0.0.1:9533";
const API = process.env.INST_API || "http://127.0.0.1:8771";
const PW = process.env.INST_PASSWORD || "inst123456";

test.use({ viewport: { width: 1440, height: 900 } });

let token = "";

async function loginApi(request: APIRequestContext, username: string): Promise<string> {
  const res = await request.post(`${API}/api/inst/auth/login`, {
    data: { username, password: PW },
  });
  expect(res.ok(), `机构登录失败 ${username} HTTP ${res.status()}`).toBeTruthy();
  const data = await res.json();
  expect(data.token).toBeTruthy();
  return data.token;
}

test.beforeAll(async ({ request }) => {
  token = await loginApi(request, "inst_manager");
});

async function login(page: import("@playwright/test").Page) {
  await page.addInitScript((t) => sessionStorage.setItem("svquant_inst_token", t), token);
}

test("v3 侧栏三组、八项，顺序固定", async ({ page }) => {
  await login(page);
  await page.goto(`${BASE}/inst`, { waitUntil: "networkidle" });
  await expect(page.locator("aside.v3-side nav.v3-nav a span:nth-child(2)")).toHaveText([
    "投资工作台",
    "项目流水线",
    "价值分析",
    "多空辩论",
    "投委会审批",
    "执行成交",
    "投资管理",
    "流程与权限",
  ]);
  await expect(page.locator(".v3-nav-label").filter({ hasText: "投资工作空间" })).toBeVisible();
  await expect(page.locator(".v3-nav-label").filter({ hasText: "流程工作台" })).toBeVisible();
  await expect(page.locator(".v3-nav-label").filter({ hasText: "规则与说明" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "投资工作台" })).toBeVisible();
});

test("八个入口可达", async ({ page }) => {
  await login(page);
  const pages: Array<[string, string]> = [
    ["/inst", "INVESTMENT OFFICE"],
    ["/inst/pipeline", "PIPELINE"],
    ["/inst/research", "RESEARCH"],
    ["/inst/debate", "DEBATE"],
    ["/inst/approvals", "DECISION"],
    ["/inst/execute", "EXECUTION"],
    ["/inst/manage", "OWNERSHIP"],
    ["/inst/playbook", "PLAYBOOK / RULES"],
  ];
  for (const [path, eyebrow] of pages) {
    await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
    await expect(page.getByText(eyebrow, { exact: false }).first()).toBeVisible({ timeout: 20_000 });
    await expect(page.locator(".v3-page-head h1").first()).toBeVisible();
  }
});

test("右上角搜索可进入已有股票研究", async ({ page }) => {
  await login(page);
  await page.goto(`${BASE}/inst`, { waitUntil: "networkidle" });
  await page.getByPlaceholder("搜索股票代码或名称…").fill("平安银行");
  const panel = page.locator(".v3-search-pop");
  await expect(panel).toBeVisible({ timeout: 20_000 });
  await expect(panel.getByText("000001.SZ", { exact: false })).toBeVisible();
  await panel.locator(".v3-search-item").first().click();
  await expect(page).toHaveURL(/\/inst\/research\?key=case(:|%3A)\d+/);
  await expect(page.locator(".v3-page-head h1").first()).toBeVisible();
});

test("流水线卡片进入只读结果页", async ({ page }) => {
  await login(page);
  await page.goto(`${BASE}/inst/pipeline`, { waitUntil: "networkidle" });
  const card = page.locator("a.v3-project").first();
  await expect(card).toBeVisible({ timeout: 20_000 });
  await card.click();
  await expect(page).toHaveURL(/\/inst\/pipeline\/result\?key=/);
  await expect(page.locator(".v3-stepper .v3-step")).toHaveCount(6);
  await expect(page.getByText("当前阶段结论", { exact: true })).toBeVisible();
  await expect(page.getByText("版本与锁定", { exact: true })).toBeVisible();
  await expect(page.getByText("下一关", { exact: true })).toBeVisible();
});

test("单流程视图项目横向排列", async ({ page }) => {
  await login(page);
  await page.goto(`${BASE}/inst/pipeline`, { waitUntil: "networkidle" });
  await page.locator(".v3-rail-cell").nth(2).click();
  await expect(page.locator(".v3-board.single")).toBeVisible();
  const cards = page.locator(".v3-col-items.horizontal .v3-project");
  await expect(cards.first()).toBeVisible({ timeout: 20_000 });
  const count = await cards.count();
  expect(count, "单流程下应有项目卡片").toBeGreaterThan(1);
  const first = await cards.nth(0).boundingBox();
  const second = await cards.nth(1).boundingBox();
  expect(first && second).toBeTruthy();
  expect(Math.round(first!.y), "单流程项目应横向排列").toBe(Math.round(second!.y));
});

test("旧入口重定向到 v3", async ({ page }) => {
  await login(page);
  const redirects: Array<[string, RegExp]> = [
    ["/inst/overview", /\/inst$/],
    ["/inst/ideas", /\/inst\/pipeline$/],
    ["/inst/portfolio", /\/inst\/manage/],
    ["/inst/execution", /\/inst\/execute/],
    ["/inst/monitor", /\/inst\/manage/],
    ["/inst/about", /\/inst\/playbook/],
    ["/inst/audit", /\/inst\/playbook/],
    ["/inst-v3", /\/inst$/],
  ];
  for (const [path, expected] of redirects) {
    await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
    await expect(page).toHaveURL(expected);
    await expect(page.locator(".v3-page-head h1").first()).toBeVisible({ timeout: 20_000 });
  }
});

test("宽屏内容区铺满，不使用窄版居中", async ({ page }) => {
  await login(page);
  await page.setViewportSize({ width: 1920, height: 1000 });
  await page.goto(`${BASE}/inst/research`, { waitUntil: "networkidle" });
  const main = await page.locator(".v3-main").boundingBox();
  expect(main, "找不到 v3 内容区").toBeTruthy();
  expect(main!.width, "1920 宽屏下内容区被 max-width 限制").toBeGreaterThan(1500);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});

test("机构端 1440 / 400 无横向溢出", async ({ page }) => {
  await login(page);
  for (const width of [1440, 400]) {
    await page.setViewportSize({ width, height: 900 });
    for (const path of [
      "/inst",
      "/inst/pipeline",
      "/inst/research",
      "/inst/debate",
      "/inst/approvals",
      "/inst/execute",
      "/inst/manage",
      "/inst/playbook",
    ]) {
      await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
      await expect(page.locator(".v3-page-head h1").first()).toBeVisible({ timeout: 20_000 });
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      );
      expect(overflow, `${path} @${width}px 横向溢出 ${overflow}px`).toBeLessThanOrEqual(1);
    }
  }
});
