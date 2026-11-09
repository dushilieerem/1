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
    ["/inst", "INVESTMENT OFFICE / 00"],
    ["/inst/pipeline", "PIPELINE / 01"],
    ["/inst/research", "RESEARCH / 02"],
    ["/inst/debate", "DEBATE / 03"],
    ["/inst/approvals", "DECISION / 04"],
    ["/inst/execute", "EXECUTION / 05"],
    ["/inst/manage", "OWNERSHIP / 06"],
    ["/inst/playbook", "PLAYBOOK / RULES"],
  ];
  for (const [path, eyebrow] of pages) {
    await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
    await expect(page.getByText(eyebrow, { exact: false }).first()).toBeVisible({ timeout: 20_000 });
    await expect(page.locator(".v3-page-head h1").first()).toBeVisible();
  }
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
