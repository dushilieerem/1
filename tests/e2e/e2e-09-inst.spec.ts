import { expect, test } from "@playwright/test";

/**
 * 主观机构端 E2E 冒烟：登录、侧栏顺序、九个工作区可达。
 * 默认连本地 Vite 9533 + 后端 8771；可用 INST_BASE / INST_API 覆盖。
 */
const BASE = process.env.INST_BASE || "http://127.0.0.1:9533";
const API = process.env.INST_API || "http://127.0.0.1:8771";
const USER = process.env.INST_USER || "inst_manager";
const PW = process.env.INST_PASSWORD || "inst123456";

test.use({ viewport: { width: 1440, height: 900 } });

let token = "";

test.beforeAll(async ({ request }) => {
  const res = await request.post(`${API}/api/inst/auth/login`, {
    data: { username: USER, password: PW },
  });
  expect(res.ok(), `机构登录失败 HTTP ${res.status()}`).toBeTruthy();
  const data = await res.json();
  token = data.token;
  expect(token).toBeTruthy();
});

async function login(page: import("@playwright/test").Page) {
  await page.addInitScript((t) => sessionStorage.setItem("svquant_inst_token", t), token);
}

test("机构端侧栏名称与顺序", async ({ page }) => {
  await login(page);
  await page.goto(`${BASE}/inst/overview`, { waitUntil: "networkidle" });
  await expect(page.locator("aside nav a")).toHaveText([
    "投资总览",
    "机会发现",
    "公司研究",
    "投资辩论室",
    "投委会审批",
    "交易执行",
    "投资组合",
    "投后管理",
    "Agent能力",
  ]);
  await expect(page.getByText("以企业为起点，以证据做决策")).toBeVisible();
});

test("研究、审批、执行、投后、Agent能力页面可达", async ({ page }) => {
  await login(page);
  for (const [path, text] of [
    ["/inst/research", "公司研究"],
    ["/inst/approvals", "投委会审批"],
    ["/inst/execution", "交易执行"],
    ["/inst/monitor", "投后管理"],
    ["/inst/about", "Agent能力"],
  ]) {
    await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
    await expect(page.getByText(text, { exact: false }).first()).toBeVisible({ timeout: 20_000 });
  }
});

test("机构端无横向溢出", async ({ page }) => {
  await login(page);
  await page.goto(`${BASE}/inst/overview`, { waitUntil: "networkidle" });
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});
