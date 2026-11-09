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

test("首页改版：今日卡/概览/热点，底部不再有我的", async ({ page }) => {
  await loginByToken(page);
  await page.route("**/api/invest/home*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        dataDate: "2026-11-04", dataSource: "Public EOD", isDemo: false, isStale: false,
        ageDays: 0, ageTradingDays: 0, user: { id: 2, name: "Demo user" },
        market: "CN", hasQuotes: true,
        portfolioSnapshot: {
          hasHoldings: true, holdingCount: 3, dailyChange: 0.86, totalValue: 386000,
          riskScore: 62, lastCheckupDate: "2026-10-24",
        },
        marketPulse: {
          asOf: "2026-11-04", status: "close", statusLabel: "收盘", statusLabelEn: "Close",
          indices: [
            { code: "000001.SH", label: "上证指数", label_en: "SSE Composite", value: 3345.67, change: -0.12, available: true },
            { code: "399001.SZ", label: "深证成指", label_en: "SZSE Component", value: 10876.54, change: 0.34, available: true },
            { code: "399006.SZ", label: "创业板指", label_en: "ChiNext", value: 2214.8, change: 1.12, available: true },
          ],
          turnover: {
            value: 17029.1, change: -4.5, available: true, note: "",
            basis: "index", basisLabel: "沪深两市成交额（指数口径）",
            basisLabelEn: "SSE + SZSE turnover (index basis)",
          },
        },
        daily: [
          { source: "stock", tag: "自选 · 事件", title: "宁德时代 10-30 预约披露", detail: "距预约披露 4 天，关注财报与现金流。", link: { type: "stock", id: "300750" } },
          { source: "portfolio", tag: "组合 · 体检", title: "行业集中度偏高", detail: "新能源合计 42.0%（阈值 40%），超出阈值 2.0。", link: { type: "portfolio" } },
          { source: "market", tag: "市场 · 成交", title: "两市成交额 1.70 万亿", detail: "较上一交易日 -4.5%", link: null },
        ],
        review: {
          title: "收盘复盘", line: "沪深300 -0.20%，组合 +0.86%。",
          summary: "沪深300 收盘 -0.20%；组合今日 +0.86%，风险主要来自行业集中。",
          facts: ["组合总资产 38.6 万元，风险分 62。", "数据为收盘后快照，不是实时行情。"],
        },
        topics: [
          { id: "ai", name: "AI 算力", summary: "算力与模型迭代驱动的产业链热度", heat: 86, valuationPercentile: 88, turnoverPercentile: 72, riskTags: [{ label: "估值偏高", label_en: "Valuation elevated", tone: "red" }] },
          { id: "dividend", name: "高股息", summary: "现金流与分红确定性", heat: 64, valuationPercentile: 42, turnoverPercentile: 38, riskTags: [{ label: "估值分位 42%", label_en: "Valuation percentile 42%", tone: "gray" }] },
          { id: "new-energy", name: "新能源", summary: "供需与价格周期", heat: 58, valuationPercentile: 35, turnoverPercentile: 61, riskTags: [{ label: "估值分位 35%", label_en: "Valuation percentile 35%", tone: "gray" }] },
        ],
        learn: { title: "估值分位：贵不贵，跟什么比？", titleEn: "Valuation percentile: expensive versus what?", link: "/learn" },
      }),
    }),
  );
  await page.goto(`${H5}/`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".today-card")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".today-mine-main b")).toHaveText("+0.86%");
  await expect(page.getByText("上次体检")).toBeVisible();
  await expect(page.getByText("上证指数")).toBeVisible();
  await expect(page.getByText("两市成交", { exact: true })).toBeVisible();
  await expect(page.getByText("沪深两市成交额（指数口径）")).toBeVisible();
  await expect(page.locator(".overview-row")).toHaveCount(3);
  await expect(page.locator(".hot-row")).toHaveCount(3);
  await expect(page.locator(".card")).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: "底部导航" }).getByText("我的")).toHaveCount(0);
  await page.getByRole("button", { name: "查看完整日报" }).click();
  await expect(page.getByText("规则生成 · 历史 EOD 数据 · 不构成投资建议")).toBeVisible();
  await page.getByRole("button", { name: "关闭" }).click();
  await page.setViewportSize({ width: 360, height: 800 });
  await noHorizontalOverflow(page);
  await page.getByRole("button", { name: "我的", exact: true }).click();
  await expect(page.getByRole("heading", { name: "我的" })).toBeVisible({ timeout: 20_000 });
});

test("首页热点「全部」进入热点列表页", async ({ page }) => {
  await loginByToken(page);
  await page.route("**/api/invest/topics", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        dataDate: "2026-11-04",
        items: [
          { id: "ai", name: "AI 算力", summary: "算力与模型迭代驱动的产业链热度", heat: 86, riskTags: [{ label: "估值偏高", label_en: "Valuation elevated", tone: "red" }] },
          { id: "dividend", name: "高股息", summary: "现金流与分红确定性", heat: 64, riskTags: [{ label: "估值分位 42%", label_en: "Valuation percentile 42%", tone: "gray" }] },
          { id: "new-energy", name: "新能源", summary: "供需与价格周期", heat: 58, riskTags: [{ label: "估值分位 35%", label_en: "Valuation percentile 35%", tone: "gray" }] },
        ],
        disclaimer: "收盘数据 · 非实时 · 非投资建议",
      }),
    }),
  );
  await page.goto(`${H5}/topics`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "今日热点" })).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".list-hot-row")).toHaveCount(3);
  await expect(page.getByText("估值偏高")).toBeVisible();
  await noHorizontalOverflow(page);
  await page.setViewportSize({ width: 360, height: 800 });
  await noHorizontalOverflow(page);
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

test("量化研究入口页展示今日关注与五个入口", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/quant`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "量化研究" })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".quant-entry")).toHaveCount(5);
  await expect(page.locator(".quant-entry").last()).toContainText("社区");
  await expect(page.locator(".quant-focus-bar")).toBeVisible();
  await expect(page.locator(".quant-style-card")).toHaveCount(0);
  await expect(page.locator(".tab.on")).toContainText("量化");
  await page.locator(".quant-entry").last().click();
  await expect(page.getByRole("heading", { name: "社区" })).toBeVisible({ timeout: 20_000 });
  await noHorizontalOverflow(page);
});

test("因子页展示市场风格与 6 行因子榜", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/quant/factors`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "因子" })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".quant-factor-row")).toHaveCount(6, { timeout: 30_000 });
  await expect(page.getByText("因子入门")).toBeVisible();
  await expect(page.locator(".quant-factor-cta")).toBeVisible();
  await expect(page.getByText(/过去一段时间涨得相对好的股票|价格起伏越小|盈利效率/).first()).toBeVisible();
  await page.locator(".quant-factor-row").first().click();
  await expect(page.locator(".quant-detail")).toBeVisible({ timeout: 20_000 });
  await noHorizontalOverflow(page);
});

test("策略页四个分区可切换", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/quant/strategies?tab=quick`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("一句话建策略")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "我的策略", exact: true }).click();
  await expect(page.getByText("还没有跟踪中的策略")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "草稿", exact: true }).click();
  await expect(page.getByText("在上面的快速实验里跑完一次")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "策略广场", exact: true }).click();
  await expect(page.locator(".quant-plaza-card, .state-box").first()).toBeVisible({ timeout: 30_000 });
  await noHorizontalOverflow(page);
});

test("快速实验：因子卡方向、配置预览与权重输入", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/quant/strategies?tab=quick`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".quant-pick").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".quant-pick")).toHaveCount(6);
  await page.locator(".quant-pick").nth(0).click();
  await page.locator(".quant-pick").nth(1).click();
  await expect(page.locator(".pick-dir")).toHaveCount(2);
  await expect(page.getByText("分散度不错", { exact: false }).or(page.getByText("重复暴露", { exact: false }))).toBeVisible();
  await page.getByRole("button", { name: /下一步：生成配置/ }).click();
  await expect(page.getByText("配置预览")).toBeVisible();
  await expect(page.locator(".seg button", { hasText: "前 10 只" })).toBeVisible();
  await expect(page.getByText("调仓：", { exact: false })).toBeVisible();
  await page.locator(".seg button", { hasText: "自定义" }).click();
  await expect(page.locator(".quant-weight-row input")).toHaveCount(2);
  await page.getByRole("button", { name: /返回修改/ }).click();
  await expect(page.getByText("选择因子")).toBeVisible();
  await noHorizontalOverflow(page);
});

test("回测与模拟盘空态明确，且模拟盘标注模拟", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/quant/backtests`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("还没有回测记录")).toBeVisible({ timeout: 30_000 });
  await page.goto(`${H5}/quant/papers`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("还没有模拟盘")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("不接券商").first()).toBeVisible();
  await noHorizontalOverflow(page);
});

test("AI 记忆入口从我的移到管家工具条，首页不再有 AI 今日解读", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/me`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("AI 记忆")).toHaveCount(0);
  await page.goto(`${H5}/`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("AI 今日解读")).toHaveCount(0);
  await page.goto(`${H5}/ai`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("button", { name: "记忆" })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("button", { name: "深度" })).toBeVisible();
  await noHorizontalOverflow(page);
});

test("个股透视 P0：3×3 快照、财务/资金/简况切换，不显示无数据模块", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/stock/600519`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".stock-head")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".stock-quote-cell")).toHaveCount(9);
  const quoteBox = await page.locator(".stock-quote").boundingBox();
  expect(quoteBox?.height || 0).toBeLessThanOrEqual(62);
  await expect(page.locator(".stock-seg button", { hasText: "财务" })).toBeVisible();
  await expect(page.locator(".stock-seg button", { hasText: "资金" })).toBeVisible();
  await page.locator(".stock-seg button", { hasText: "财务" }).click();
  await expect(page.locator(".fin-trend-tabs button")).toHaveCount(8);
  await expect(page.locator(".fin-trend-svg")).toBeVisible();
  await expect(page.locator(".fin-period-select > button")).toContainText("三季报");
  await page.locator(".fin-period-select > button").click();
  await page.locator(".fin-period-menu button", { hasText: "年报" }).click();
  await expect(page.locator(".fin-period-select > button")).toContainText("年报");
  await page.locator(".stock-seg button", { hasText: "资金" }).click();
  await expect(page.getByText("主力资金")).toBeVisible();
  await expect(page.getByText("近 20 日主力净流入")).toBeVisible();
  await page.locator(".stock-seg button", { hasText: "简况" }).click();
  await expect(page.getByText("同业比较")).toBeVisible();
  await expect(page.getByText("股东", { exact: false })).toHaveCount(0);
  await expect(page.getByText("分红", { exact: false })).toHaveCount(0);
  await noHorizontalOverflow(page);
});

test("个股 AI 解读进入页面自动生成", async ({ page }) => {
  await loginByToken(page);
  await page.route("**/api/invest/ai/stock/**", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ ok: true, card: { summary: "估值处于历史中位，关注盈利稳定性。", sections: [] } }),
    }),
  );
  await page.goto(`${H5}/stock/600519`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("估值处于历史中位，关注盈利稳定性。")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: "生成 AI 解读" })).toHaveCount(0);
  await noHorizontalOverflow(page);
});

test("Agent 管理页展示 Agent 与提示词编辑", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/agents`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Agent 管理" })).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".agent-card").first()).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".agent-prompt").first()).toBeVisible();
  const prompt = page.locator(".agent-prompt").first();
  await prompt.fill("只讲最关键的估值风险，不展开。");
  await page.getByRole("button", { name: "保存" }).first().click();
  await expect(page.getByText(/已保存/)).toBeVisible({ timeout: 20_000 });
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

test("AI 回答自动渲染毛利率柱图与估值分位", async ({ page }) => {
  await loginByToken(page);
  await page.route("**/api/invest/ai/chat", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ok: true, intent: "stock",
        card: { summary: "毛利率近四期保持在 90% 左右。", sections: [] },
        charts: [
          { type: "bar", title: "近 4 期毛利率", labels: ["2025Q1", "2025Q2", "2025Q3", "2025Q4"], values: [91.2, 90.8, 91.5, 90.9], unit: "%" },
          { type: "percentile", title: "PE(TTM) 与历史分位", value: 22.1, percentile: 40, unit: "x" },
        ],
      }),
    }),
  );
  await page.goto(`${H5}/ai`, { waitUntil: "domcontentloaded" });
  await page.getByPlaceholder("问个股、组合、复盘或条件选股").fill("贵州茅台毛利率怎么样");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.locator(".ai-bars i")).toHaveCount(4, { timeout: 20_000 });
  await expect(page.locator(".ai-percentile")).toBeVisible();
  await expect(page.getByText("40% 分位")).toBeVisible();
  await noHorizontalOverflow(page);
});

test("AI 截图识图填入输入框，不自动发送", async ({ page }) => {
  await loginByToken(page);
  await page.route("**/api/invest/ai/vision", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        text: "分析 宁德时代(300750)",
        corrections: [{ from: "宁德", to: "宁德时代" }],
        model: "vision-test",
      }),
    }),
  );
  await page.goto(`${H5}/ai`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: /全部/ }).click();
  await expect(page.getByText("截图识图")).toBeVisible({ timeout: 20_000 });
  await page.locator(".vision-panel input[type=file]").setInputFiles({
    name: "stock.png",
    mimeType: "image/png",
    buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZlqkAAAAASUVORK5CYII=", "base64"),
  });
  await expect(page.locator(".vision-preview img")).toBeVisible();
  await page.getByRole("button", { name: "识别并填入" }).click();
  await expect(page.getByPlaceholder("问个股、组合、复盘或条件选股")).toHaveValue("分析 宁德时代(300750)", { timeout: 20_000 });
  await expect(page.getByText("已识图并校正", { exact: false })).toBeVisible();
  await expect(page.locator(".ai-msg.user")).toHaveCount(0);
  await noHorizontalOverflow(page);
});

test("AI 管家实时语音识别写入输入框，不自动发送", async ({ page }) => {
  await loginByToken(page);
  await page.addInitScript(() => {
    class FakeSpeechRecognition {
      lang = "";
      continuous = false;
      interimResults = false;
      maxAlternatives = 1;
      onstart: (() => void) | null = null;
      onresult: ((event: any) => void) | null = null;
      onerror: ((event: any) => void) | null = null;
      onend: (() => void) | null = null;
      start() {
        this.onstart?.();
        setTimeout(() => {
          this.onresult?.({ results: [[{ transcript: "贵州茅台" }]] });
          this.onend?.();
        }, 30);
      }
      stop() { this.onend?.(); }
      abort() { this.onend?.(); }
    }
    (window as any).SpeechRecognition = FakeSpeechRecognition;
    (window as any).webkitSpeechRecognition = FakeSpeechRecognition;
  });
  await page.goto(`${H5}/ai`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "语音输入" }).click();
  await expect(page.locator(".ai-composer textarea")).toHaveValue("贵州茅台", { timeout: 10_000 });
  await expect(page.locator(".ai-msg.user")).toHaveCount(0);
  await noHorizontalOverflow(page);
});

test("AI 管家选股：面板填句 → 条件卡 → 结果卡与行业分布", async ({ page }) => {
  await loginByToken(page);
  await page.route("**/api/invest/condition/screen", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        status: "ok",
        query: "PE 分位低于 30%，近 3 年净利润连续增长，ROE 大于 10%",
        conditions: [
          { key: "pe_percentile", label: "PE 分位", label_en: "PE percentile", op: "max", value: 30, unit: "%", text: "PE 分位 ≤ 30%", supported: true },
          { key: "profit_growth_years", label: "近 3 年净利润连续增长", label_en: "Profit growth streak", op: "bool", value: 3, text: "近 3 年净利润连续增长", supported: true },
          { key: "roe", label: "ROE", label_en: "ROE", op: "min", value: 10, unit: "%", text: "ROE ≥ 10%", supported: true },
        ],
        count: 2,
        items: [
          { code: "600519", name: "贵州茅台", industry: "食品饮料", price: 1439.1, change_pct: 1.2, roe: 30.1 },
          { code: "000001", name: "平安银行", industry: "银行", price: 11.2, change_pct: -0.4, roe: 11.5 },
        ],
        summary: ["共筛出 2 只，按条件逐项过滤。", "总市值中位数 461 亿。"],
        risk: "筛选基于历史 EOD 数据，不含实时与资金流；结果非投资建议。",
        industry_distribution: [
          { name: "食品饮料", count: 1, pct: 50 },
          { name: "银行", count: 1, pct: 50 },
        ],
        followups: ["这批股票属于哪些行业", "按 ROE 从高到低看", "把条件放宽一点"],
      }),
    }),
  );
  await page.goto(`${H5}/ai`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "打开条件选股" }).click();
  await expect(page.getByText("条件选股").last()).toBeVisible();
  await expect(page.getByText("低估优选")).toBeVisible();
  await page.getByRole("button", { name: /低估优选/ }).click();
  const input = page.locator(".ai-composer textarea");
  await expect(input).toHaveValue("PE 分位低于 30%，近 3 年净利润连续增长，ROE 大于 10%");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("按你设定的 3 个条件，共筛出 2 只。")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".condition-tag")).toHaveCount(3);
  await expect(page.getByText("贵州茅台")).toBeVisible();
  await page.getByRole("button", { name: /这批股票属于哪些行业/ }).click();
  await expect(page.getByText("行业分布 · 申万一级")).toBeVisible();
  await noHorizontalOverflow(page);
  await page.setViewportSize({ width: 360, height: 800 });
  await noHorizontalOverflow(page);
});

test("AI 管家直接输入条件句也会进入筛选", async ({ page }) => {
  await loginByToken(page);
  await page.route("**/api/invest/condition/screen", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ok: true, status: "too_broad", count: 355,
        conditions: [{ key: "pe_percentile", label: "PE 分位", op: "max", value: 30, unit: "%", text: "PE 分位 ≤ 30%", supported: true }],
        diagnostic: {
          blocking: "条件偏松",
          suggestion: "当前范围超过 200 只，再补一条估值、盈利或成交条件即可收窄。",
          relax_actions: [{ type: "add", query: "ROE 大于 10%", label: "加一条 ROE 大于 10%" }],
        },
        risk: "历史 EOD 数据。",
      }),
    }),
  );
  await page.goto(`${H5}/ai`, { waitUntil: "domcontentloaded" });
  await page.locator(".ai-composer textarea").fill("PE 分位低于 30% 的股票");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("355 只 · 条件偏松")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/超过 200 只上限/)).toBeVisible();
  await noHorizontalOverflow(page);
});

test("AI 管家选股：资金流预设可用并展示条件", async ({ page }) => {
  await loginByToken(page);
  await page.route("**/api/invest/condition/screen", (route) => {
    const body = route.request().postDataJSON();
    return route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        status: "ok",
        conditions: body.conditions || [
          { key: "market_cap", label: "总市值", op: "max", value: 200, unit: "亿", text: "总市值 ≤ 200亿", supported: true },
          { key: "return_20d", label: "近 20 日涨幅", op: "min", value: 10, unit: "%", text: "近 20 日涨幅 ≥ 10%", supported: true },
          { key: "main_net_inflow_5d", label: "5 日主力净流入", op: "min", value: 5000, unit: "万", text: "5 日主力净流入 ≥ 5000万", supported: true },
        ],
        count: 1,
        items: [{ code: "600519", name: "贵州茅台", industry: "食品饮料", price: 1439.1, change_pct: 1.2 }],
        summary: ["共筛出 1 只。"],
        risk: "历史 EOD 数据。",
        industry_distribution: [{ name: "食品饮料", count: 1, pct: 100 }],
        followups: ["这批股票属于哪些行业", "按 ROE 从高到低看", "把条件放宽一点"],
      }),
    });
  });
  await page.goto(`${H5}/ai`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "打开条件选股" }).click();
  await expect(page.getByRole("button", { name: /小市值弹性/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /主力连续流入/ })).toBeVisible();
  await page.getByRole("button", { name: /小市值弹性/ }).click();
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("按你设定的 3 个条件，共筛出 1 只。")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("5 日主力净流入", { exact: true })).toBeVisible();
  await noHorizontalOverflow(page);
});

test("多标的对比页渲染同口径维度、亮点与总结", async ({ page }) => {
  await loginByToken(page);
  const payload = {
    ok: true,
    items: [
      { code: "600519", name: "贵州茅台", industry: "食品饮料" },
      { code: "300750", name: "宁德时代", industry: "电力设备" },
    ],
    dimensions: [
      {
        key: "market", title: "行情表现", title_en: "Market performance",
        rows: [
          { key: "price", label: "最新价", label_en: "Price", fmt: "price", values: [1452.0, 300.0], missing: [] },
          { key: "return5", label: "5 日涨跌", label_en: "5-day return", fmt: "pct", values: [2.1, -1.3], missing: [] },
        ],
        missing: [],
      },
      {
        key: "valuation", title: "估值水平", title_en: "Valuation",
        rows: [
          { key: "pe", label: "PE(TTM)", label_en: "PE (TTM)", fmt: "x", values: [22.0, null], missing: ["宁德时代"] },
        ],
        missing: [{ code: "300750", name: "宁德时代", labels: ["PE(TTM)"] }],
      },
    ],
    highlights: [
      { code: "600519", name: "贵州茅台", positive: [{ text: "毛利率 91.0%，处于较高水平", tone: "good" }], negative: [] },
      { code: "300750", name: "宁德时代", positive: [], negative: [{ text: "PE 分位 80%，处于近 3 年较高位置", tone: "amber" }] },
    ],
    summary: [{ text: "营收同比：贵州茅台 +1.3%，宁德时代 +54.8%。" }, { text: "标的属于不同行业，以上只描述各自水平，不并排比大小。" }],
    note: "公告与研报数据尚未接入。",
    disclaimer: "以上对比仅描述数据差异，不构成投资建议。",
  };
  await page.route("**/api/invest/compare**", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(payload) }),
  );
  await page.goto(`${H5}/compare/600519/300750`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".compare-table")).toHaveCount(2, { timeout: 20_000 });
  await expect(page.getByRole("heading", { name: "行情表现" })).toBeVisible();
  await expect(page.getByText("宁德时代 缺：PE(TTM)")).toBeVisible();
  await expect(page.getByText("毛利率 91.0%，处于较高水平")).toBeVisible();
  await expect(page.getByText("标的属于不同行业，以上只描述各自水平，不并排比大小。")).toBeVisible();
  await expect(page.getByText("以上对比仅描述数据差异，不构成投资建议。")).toBeVisible();
  await noHorizontalOverflow(page);
});

test("AI 多空分析分利多/利空两组且不站队", async ({ page }) => {
  await loginByToken(page);
  await page.route("**/api/invest/ai/chat", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        intent: "debate",
        debate: {
          code: "600519", name: "贵州茅台",
          bull: [{ text: "营收同比 +10.1%，收入仍在增长", source: "财报", tone: "green" }],
          bear: [{ text: "PE 分位 80%，处于近 3 年较高位置", source: "估值", tone: "amber" }],
          note: "公告与研报数据尚未接入。",
          footer: "双方都有证据，不构成任何方向的建议。",
        },
        card: { summary: "贵州茅台的利多与利空均有数据依据，不站队。", sections: [] },
      }),
    }),
  );
  await page.goto(`${H5}/ai`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "贵州茅台多空" }).click();
  await expect(page.getByRole("heading", { name: "贵州茅台 · 多空分析" })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("营收同比 +10.1%，收入仍在增长")).toBeVisible();
  await expect(page.getByText("PE 分位 80%，处于近 3 年较高位置")).toBeVisible();
  await expect(page.getByText("双方都有证据，不构成任何方向的建议。")).toBeVisible();
  await noHorizontalOverflow(page);
});

test("AI 预设问法的参数位可点击替换", async ({ page }) => {
  await loginByToken(page);
  await page.goto(`${H5}/ai`, { waitUntil: "domcontentloaded" });
  await page.locator(".ai-template-bar").getByRole("button", { name: "个股解读" }).click();
  await expect(page.locator(".param-mark").filter({ hasText: "标的" })).toBeVisible();
  await page.locator(".param-mark").filter({ hasText: "标的" }).click();
  const selected = await page.locator(".ai-composer textarea").evaluate((el: HTMLTextAreaElement) => ({
    start: el.selectionStart,
    end: el.selectionEnd,
    value: el.value,
  }));
  expect(selected.value.slice(selected.start, selected.end)).toBe("标的");
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
  for (const path of ["/", "/watch", "/portfolio", "/news", "/learn", "/me", "/quant", "/quant/factors", "/quant/strategies?tab=quick", "/quant/strategies?tab=plaza", "/quant/backtests", "/quant/papers", "/agents", "/community", "/compare/600519/300750"]) {
    await page.goto(`${H5}${path}`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(350);
    await noHorizontalOverflow(page);
  }
  await page.goto(`${H5}/stock/600036`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".stock-head-title span")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".stock-head-title span")).not.toContainText(/\d{6}\.SI/);
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
