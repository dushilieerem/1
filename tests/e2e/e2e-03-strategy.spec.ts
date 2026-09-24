import { test, expect } from "@playwright/test";
import {
  FE, RUN_ID, USER_A, USER_B, PW,
  api, registerUser, reUp, blockStep, loginUi, noSecretLeak, pageFetch,
} from "./helpers/r5";

/**
 * E2E-03 策略回测与广场（用户流程二：创建/运行策略/查看结果 + 三：结果保存/历史查询）
 * 关联用例：TC-STRATEGY-001/004/008/011/013/014/018
 * 事务步骤以登录态浏览器 fetch（前端同源 /api 代理）驱动，真实走 前端→后端→DB。
 */

let tokenA = "";
let tokenB = "";
let projectId = 0;
let runId = "";
let plazaId = 0;
const PROJ_NAME = `${RUN_ID}_proj`;
const RUN_NAME = `${RUN_ID}_run`;
const PLAZA_TITLE = `${RUN_ID}_plaza`;

test.beforeAll(async ({ request }) => {
  tokenA = (await registerUser(request, USER_A, PW)).token;
  tokenB = (await registerUser(request, USER_B, PW)).token;
});

test.afterAll(async ({ request }) => {
  if (plazaId) await api(request, "DELETE", `/api/strategy/plaza/${plazaId}`, { token: tokenA });
  if (runId) await api(request, "DELETE", `/api/strategy/runs/${runId}`, { token: tokenA });
  if (projectId) await api(request, "DELETE", `/api/strategy/projects/${projectId}`, { token: tokenA });
});

test("策略研究列表页加载（UI，登录态）", async ({ page }) => {
  await loginUi(page, USER_A, PW);
  await page.goto(FE + "/strategy/research");
  await expect(page.locator("body")).toContainText(/策略|研究/, { timeout: 20_000 });
});

test("创建策略项目并更新配置（登录态浏览器 fetch→DB）", async ({ page }) => {
  await loginUi(page, USER_A, PW);
  const created = await pageFetchJson(page, "POST", "/api/strategy/projects", tokenA, { name: PROJ_NAME });
  expect(created.status).toBe(200);
  projectId = created.json?.project?.id;
  expect(projectId).toBeTruthy();

  const upd = await pageFetchJson(page, "PUT", `/api/strategy/projects/${projectId}`, tokenA, {
    name: PROJ_NAME,
    description: "R5 E2E",
    config: { universe: "CSI300" },
  });
  expect(upd.status).toBe(200);

  // 数据库落库验证：通过后端查询接口读回
  const got = await pageFetchJson(page, "GET", `/api/strategy/projects/${projectId}`, tokenA);
  expect(got.status).toBe(200);
  expect(got.json?.project?.name).toBe(PROJ_NAME);
});

test("内置策略库可读（RE 依赖）", async ({ request }, testInfo) => {
  if (!(await reUp(request))) await blockStep(testInfo, "RE 不可达：内置策略库 BLOCKED");
  const r = await api(request, "GET", "/api/strategy/library", { token: tokenA });
  expect(r.status).toBe(200);
  expect(noSecretLeak(r.json)).toBeTruthy();
});

test("保存策略 Run、查询与历史（登录态 fetch + 报告页 UI）", async ({ page }) => {
  test.skip(!projectId, "前置项目创建失败");
  await loginUi(page, USER_A, PW);
  const saved = await pageFetchJson(page, "POST", "/api/strategy/runs", tokenA, {
    projectId,
    name: RUN_NAME,
    request: { universe: "CSI300" },
    result: { metrics: { annual_return: 0.1 }, equity_curve: [] },
    elapsedSec: 0.01,
  });
  expect(saved.status).toBe(200);
  runId = saved.json?.run?.id;
  expect(runId).toBeTruthy();

  const got = await pageFetchJson(page, "GET", `/api/strategy/runs/${runId}`, tokenA);
  expect(got.status).toBe(200);
  expect(got.json?.run?.id ?? got.json?.run?.run_id).toBeTruthy();

  // 历史查询 UI（策略项目历史页与报告页可达）
  await page.goto(`${FE}/strategy/research/${projectId}/history`);
  await expect(page.locator("body")).toContainText(/历史|运行/, { timeout: 20_000 });
  await page.goto(`${FE}/strategy/research/report/${runId}`);
  await expect(page.locator("body")).toContainText(/报告|回测|运行/, { timeout: 20_000 });
});

test("策略广场发布、匿名浏览与越权隐藏（登录态 fetch + 匿名请求）", async ({ page, request }) => {
  await loginUi(page, USER_A, PW);
  const pub = await pageFetchJson(page, "POST", "/api/strategy/plaza", tokenA, {
    title: PLAZA_TITLE,
    body: "R5 E2E plaza item",
    snapshot: { ret: 0.1 },
  });
  expect(pub.status).toBe(200);
  plazaId = pub.json?.item?.id;
  expect(plazaId).toBeTruthy();

  // 匿名（未登录）公开浏览
  const anon = await api(request, "GET", "/api/strategy/plaza?limit=5");
  expect(anon.status).toBe(200);
  expect(JSON.stringify(anon.json)).toContain(PLAZA_TITLE);

  // 匿名无法访问广场详情接口集合管理类写操作（越权隐藏）
  const evil = await api(request, "DELETE", `/api/strategy/plaza/${plazaId}`, { token: tokenB });
  expect([403, 404]).toContain(evil.status);

  // 广场页 UI 匿名可达
  await page.goto(FE + "/strategy/plaza");
  await expect(page.locator("body")).toContainText(/策略广场|广场/, { timeout: 20_000 });
});

async function pageFetchJson(page: any, method: string, path: string, token: string, body?: unknown) {
  return pageFetch(page, method, path, token, body);
}
