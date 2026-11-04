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
    await expect(page.getByRole("heading", { name: /评论/ })).toBeVisible({ timeout: 20_000 });
    await noHorizontalOverflow(page);
  }
});

test("消息通知页可打开", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/notifications`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "消息通知" })).toBeVisible({ timeout: 20_000 });
  await noHorizontalOverflow(page);
});

test("帖子详情有举报入口（有帖子时）", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/community`, { waitUntil: "domcontentloaded" });
  const first = page.locator(".post-row").first();
  if (await first.count()) {
    await first.click();
    await expect(page.getByRole("button", { name: "举报帖子" })).toBeVisible({ timeout: 20_000 });
  }
});

test("量化研究入口与因子/策略库可打开", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/quant`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "量化研究" })).toBeVisible({ timeout: 20_000 });
  await page.goto(`${H5}/quant/factor`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "因子库" })).toBeVisible({ timeout: 20_000 });
  await page.goto(`${H5}/quant/strategy`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "策略库" })).toBeVisible({ timeout: 20_000 });
  await noHorizontalOverflow(page);
});

test("个股分时视图可切换（有数据或明确空态）", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/stock/600519`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "分时" }).click();
  await expect(page.locator('svg[aria-label="分时走势"], .empty-inline')).toBeVisible({ timeout: 30_000 });
  await noHorizontalOverflow(page);
});

test("ETF 穿透页展示代理成分", async ({ page }) => {
  await loginByToken(page);
  // 运行中的后端可能是旧版本；这里用固定响应验证 UI 契约
  await page.route("**/api/invest/etf/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        etf: "510300.SH",
        tracking: "index_proxy",
        tracked_index: "000300.SH",
        constituent_count: 2,
        constituents: [
          { symbol: "600519.SH", weight: 3.2 },
          { symbol: "300750.SZ", weight: 4.0 },
        ],
        warning: "代理口径",
      }),
    }),
  );
  await page.goto(`${H5}/etf/510300`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "ETF 穿透" })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("指数代理")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".data-table")).toBeVisible({ timeout: 20_000 });
  await noHorizontalOverflow(page);
});

test("AI 管家可发送问题并渲染卡片", async ({ page }) => {
  await loginByToken(page);
  await page.route("**/api/invest/ai/chat", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        intent: "stock",
        target_agent: "stock",
        card_hints: ["card", "chart"],
        card: {
          summary: "贵州茅台收盘上涨，估值处于历史中位。",
          sections: [{ title: "风险", body: "数据为收盘口径。" }],
          disclaimer: "AI 生成 · 非投资建议",
        },
        chart: { code: "600519", bars: [{ close: 1 }, { close: 2 }] },
      }),
    }),
  );
  await page.goto(`${H5}/ai`, { waitUntil: "domcontentloaded" });
  await page.getByPlaceholder("问个股、组合、复盘或条件选股").fill("贵州茅台怎么看");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("贵州茅台收盘上涨")).toBeVisible({ timeout: 20_000 });
  await noHorizontalOverflow(page);
});

test("多标的对比页渲染同口径表与 AI 入口", async ({ page }) => {
  await loginByToken(page);
  const stock = (code: string, name: string) => ({
    quote: { code, name, industry: "白酒", price: 100, changePct: 1.2 },
    valuation: { pe: 20, pb: 3, pePercentile: 40 },
    technical: { return20: 5, drawdown: -3 },
    report: { revenue: 100, netProfit: 20, grossMargin: 80, roe: 15 },
  });
  await page.route("**/api/invest/stock/600519", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(stock("600519", "贵州茅台")) }),
  );
  await page.route("**/api/invest/stock/300750", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(stock("300750", "宁德时代")) }),
  );
  await page.route("**/api/invest/ai/compare", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ ok: true, card: { summary: "两者估值与增速不同。", sections: [] } }),
    }),
  );
  await page.goto(`${H5}/compare/600519/300750`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".data-table")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: /生成 AI 对比解读/ }).click();
  await expect(page.getByText("两者估值与增速不同")).toBeVisible({ timeout: 20_000 });
  await noHorizontalOverflow(page);
});

test("组合页：持仓 / 体检切换与关键区块", async ({ page, request }) => {
  const headers = { Authorization: `Bearer ${token}` };
  const imported = await request.post(`${API}/api/invest/portfolio/import`, {
    headers,
    data: {
      holdings: [
        { code: "600036", shares: 4845, cost: 35 },
        { code: "510300", shares: 46046, cost: 3.75 },
        { code: "CASH", shares: 86400, cost: 1 },
      ],
    },
  });
  expect(imported.ok(), `导入组合失败 HTTP ${imported.status()}`).toBeTruthy();
  // 第二次导入改变权重，生成「最近调仓」记录
  const rebalanced = await request.post(`${API}/api/invest/portfolio/import`, {
    headers,
    data: {
      holdings: [
        { code: "600036", shares: 3000, cost: 35 },
        { code: "510300", shares: 40000, cost: 3.75 },
        { code: "CASH", shares: 120000, cost: 1 },
      ],
    },
  });
  expect(rebalanced.ok(), `再次导入组合失败 HTTP ${rebalanced.status()}`).toBeTruthy();

  await loginByToken(page);
  await page.goto(`${H5}/portfolio`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".pf-total")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("tab", { name: "持仓" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { name: "今日归因" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "行业暴露" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "最近调仓" })).toBeVisible();
  await expect(page.locator(".trade-row").first()).toBeVisible();
  await noHorizontalOverflow(page);

  await page.getByRole("tab", { name: "体检" }).click();
  await expect(page.locator(".risk-ring")).toBeVisible();
  await expect(page.getByRole("heading", { name: "诊断结论" })).toBeVisible();
  await expect(page.getByText("这意味着什么").first()).toBeVisible();
  await expect(page.getByText("风险在哪").first()).toBeVisible();
  await expect(page.getByText("下一步看什么").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "配置偏离" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "压力测试与成本" })).toBeVisible();
  await noHorizontalOverflow(page);
});

test("中英文切换：英文首页展示美股数据", async ({ page }) => {
  await loginByToken(page);
  await page.addInitScript(() => localStorage.setItem("svq_invest_locale", "en"));
  await page.route("**/api/invest/home*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        dataDate: "2026-10-29",
        dataSource: "Public EOD (US)",
        isDemo: false,
        isStale: false,
        ageDays: 0,
        ageTradingDays: 0,
        user: { id: 2, name: "Demo user" },
        daily: [{ tag: "US · top gainer", title: "Apple +1.48%", detail: "Among the most active US names.", link: { type: "stock", id: "AAPL.O" } }],
        review: { title: "US close", summary: "US EOD snapshot: breadth is positive.", facts: ["Quotes and charts only.", "Not real-time."] },
        indices: [],
        topics: [],
        watchlist: [{ code: "AAPL.O", name: "Apple", price: 348.91, changePct: 1.48, group: "Default" }],
        glossary: [],
      }),
    }),
  );
  await page.goto(`${H5}/`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: /Good afternoon/ })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Apple", { exact: false }).first()).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Bottom navigation" })).toBeVisible();
  await expect(page.locator(".locale-toggle")).toBeVisible();
  await page.locator(".locale-toggle").click();
  await expect(page.getByRole("heading", { name: /下午好/ })).toBeVisible({ timeout: 30_000 });
  await noHorizontalOverflow(page);
});

test("无美股数据时英文模式给出明确空态", async ({ page }) => {
  await loginByToken(page);
  await page.addInitScript(() => localStorage.setItem("svq_invest_locale", "en"));
  await page.route("**/api/invest/home*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        market: "US", hasQuotes: false, dataDate: "2026-11-03", dataSource: "US coverage unavailable",
        isDemo: false, user: { id: 2, name: "Demo user" }, daily: [],
        review: { title: "US quotes unavailable", summary: "No US quotes.", facts: [] },
        indices: [], topics: [], watchlist: [], glossary: [],
      }),
    }),
  );
  await page.route("**/api/invest/search*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ q: "", market: "US", available: false, results: [], presets: [], note: "No US quotes." }),
    }),
  );
  await page.goto(`${H5}/`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("US quotes not available").first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("0 up / 0 down")).toHaveCount(0);
  await page.goto(`${H5}/search`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("US quotes not available").first()).toBeVisible({ timeout: 20_000 });
  await noHorizontalOverflow(page);
});

test("学习中心术语详情有人话正文、例子与常见误用", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/learn?term=pe_ttm`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("一句话理解")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("例子", { exact: true })).toBeVisible();
  await expect(page.getByText("常见误用")).toBeVisible();
  await noHorizontalOverflow(page);
});

test("资讯页展示数据平台 news 数据集", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/news`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".news-item, .empty-inline").first()).toBeVisible({ timeout: 20_000 });
  expect(await page.locator(".news-item").count()).toBeGreaterThan(0);
  await noHorizontalOverflow(page);
});

test("英文模式可搜索并打开真实美股", async ({ page }) => {
  await loginByToken(page);
  await page.addInitScript(() => localStorage.setItem("svq_invest_locale", "en"));
  await page.goto(`${H5}/search`, { waitUntil: "domcontentloaded" });
  const input = page.getByPlaceholder("Enter a US ticker or name, e.g. AAPL");
  await input.fill("AAPL");
  await expect(page.getByText("Apple").first()).toBeVisible({ timeout: 20_000 });
  await page.getByText("Apple").first().click();
  await expect(page.getByText("AAPL.O · US equity")).toBeVisible({ timeout: 20_000 });
  await noHorizontalOverflow(page);
});

test("360 宽关键页面无横向溢出，行业代码不裸奔", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await loginByToken(page);
  for (const path of ["/", "/watch", "/portfolio", "/news", "/learn", "/me", "/quant", "/community"]) {
    await page.goto(`${H5}${path}`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(350);
    await noHorizontalOverflow(page);
  }
  await page.goto(`${H5}/stock/600036`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".page-head p")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".page-head p")).not.toContainText(/\d{6}\.SI/);
  await noHorizontalOverflow(page);
});

test("轻量因子选股页渲染规则打分", async ({ page }) => {
  await loginByToken(page);
  await page.route("**/api/invest/quant/select*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        factors: ["低估值", "高股息", "20 日动量"],
        items: [{ code: "601668", name: "中国建筑", score: 2.1, parts: [["低估值", 90]] }],
      }),
    }),
  );
  await page.goto(`${H5}/quant/select`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("中国建筑")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("低估值 90")).toBeVisible({ timeout: 20_000 });
  await noHorizontalOverflow(page);
});
