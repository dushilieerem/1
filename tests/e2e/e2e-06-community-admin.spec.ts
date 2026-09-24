import { test, expect } from "@playwright/test";
import {
  FE, RUN_ID, USER_A, USER_B, PW, ADMIN_USER, ADMIN_PW,
  api, registerUser, loginUser, loginUi, pageFetch, noSecretLeak,
} from "./helpers/r5";

/**
 * E2E-06 社区治理链路 + 管理员流程（用户流程六）
 * 关联用例：TC-COMMUNITY-005/011/013/014/016/017/019/020、TC-ADMIN-001..003、TC-SEC-020
 * 含附加断言（已批准）：浏览器渲染层 XSS 验证（回应 RISK-R3-XSS-001）。
 */

let tokenA = "";
let tokenB = "";
let tokenAdmin = "";
let postId = 0;
let xssPostId = 0;
let reportId = 0;
const POST_TITLE = `${RUN_ID}_post`;
const XSS_TITLE = `${RUN_ID}_xss`;
const XSS_PAYLOAD = `<script>window.__r5xss=1</script><img src=x onerror="window.__r5xss=2"><b>R5_XSS_MARKER</b>`;

test.beforeAll(async ({ request }) => {
  tokenA = (await registerUser(request, USER_A, PW)).token;
  tokenB = (await registerUser(request, USER_B, PW)).token;
  tokenAdmin = (await loginUser(request, ADMIN_USER, ADMIN_PW)).token;
});

test.afterAll(async ({ request }) => {
  // 帖子删除→hidden；物理清除由 r5_e2e_cleanup.py 按 R5_TEST_ 前缀执行
  for (const id of [xssPostId, postId]) {
    if (id) await api(request, "DELETE", `/api/community/posts/${id}`, { token: tokenA });
  }
});

test("普通用户发帖（UI）", async ({ page }) => {
  await loginUi(page, USER_A, PW);
  await page.goto(FE + "/community/new");
  await page.locator('input[placeholder="一句话说清你的分享"]').fill(POST_TITLE);
  await page.locator('[contenteditable="true"]').first().fill("R5 E2E community post body");
  // 板块选择器存在时选第一个有效项（默认可能为空）
  const sectionSelect = page.locator("select").first();
  if (await sectionSelect.count()) await sectionSelect.selectOption({ index: 1 }).catch(() => void 0);
  await page.getByRole("button", { name: "发布", exact: true }).first().click();
  await page.waitForURL(/\/community\/post\/\d+/, { timeout: 20_000 });
  postId = Number(page.url().match(/\/community\/post\/(\d+)/)?.[1]);
  expect(postId).toBeTruthy();
  await expect(page.getByText(POST_TITLE).first()).toBeVisible();
});

test("评论、点赞、收藏（API，双用户）", async ({ request }) => {
  test.skip(!postId, "前置发帖失败");
  const comment = await api(request, "POST", `/api/community/posts/${postId}/comments`, { token: tokenB, body: { body: `${RUN_ID} comment` } });
  expect(comment.status).toBe(200);
  const vote = await api(request, "POST", `/api/community/posts/${postId}/vote`, { token: tokenB, body: { value: 1 } });
  expect(vote.status).toBe(200);
  const fav = await api(request, "POST", `/api/community/posts/${postId}/favorite`, { token: tokenB, body: {} });
  expect(fav.status).toBe(200);
  const comments = await api(request, "GET", `/api/community/posts/${postId}/comments`);
  expect(comments.status).toBe(200);
});

test("举报与审核处置（普通用户举报→管理员处置）", async ({ request }) => {
  test.skip(!postId, "前置发帖失败");
  const report = await api(request, "POST", "/api/community/reports", {
    token: tokenB,
    body: { target_type: "post", post_id: postId, reason: "spam", detail: "R5 E2E" },
  });
  expect(report.status).toBe(200);
  reportId = report.json?.report?.id;
  expect(reportId).toBeTruthy();

  const userResolve = await api(request, "POST", `/api/community/reports/${reportId}/resolve`, { token: tokenB, body: { status: "resolved" } });
  expect(userResolve.status).toBe(403);
  const adminResolve = await api(request, "POST", `/api/community/reports/${reportId}/resolve`, { token: tokenAdmin, body: { status: "resolved" } });
  expect(adminResolve.status).toBe(200);
});

test("越权修改他人帖子被拒（IDOR）", async ({ request }) => {
  test.skip(!postId, "前置发帖失败");
  const r = await api(request, "PUT", `/api/community/posts/${postId}`, {
    token: tokenB,
    body: { title: `${RUN_ID}_hack`, body: "bad", section: "strategy" },
  });
  expect(r.status).toBe(403);
});

test("社区内容浏览器渲染 XSS 断言（附加项，回应 RISK-R3-XSS-001）", async ({ page }, testInfo) => {
  // A 发含 payload 的帖子（API 建帖，浏览器验证渲染）
  const created = await api(page.request, "POST", "/api/community/posts", {
    token: tokenA,
    body: { title: XSS_TITLE, body: XSS_PAYLOAD, section: "strategy" },
  });
  expect(created.status).toBe(200);
  xssPostId = created.json?.post?.id ?? created.json?.id;
  expect(xssPostId).toBeTruthy();

  // B 在浏览器中打开帖子：payload 不得执行，标记文本应作为文本渲染
  await loginUi(page, USER_B, PW);
  await page.goto(`${FE}/community/post/${xssPostId}`);
  await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => void 0);
  const xssFired = await page.evaluate(() => (window as any).__r5xss ?? null);
  expect(xssFired, "脚本/事件处理器不得执行").toBeNull();
  await expect(page.getByText("R5_XSS_MARKER")).toBeVisible({ timeout: 15_000 });
  testInfo.annotations.push({ type: "NOTE", description: "RISK-R3-XSS-001 浏览器渲染验证完成" });
});

test("审计日志权限矩阵与管理员查询（管理员流程）", async ({ request }) => {
  const rAdmin = await api(request, "GET", "/api/admin/logs?limit=10", { token: tokenAdmin });
  expect(rAdmin.status).toBe(200);
  expect(noSecretLeak(rAdmin.json)).toBeTruthy();
  const items = rAdmin.json?.items || rAdmin.json?.logs || [];
  expect(Array.isArray(items)).toBeTruthy();

  const rUser = await api(request, "GET", "/api/admin/logs?limit=10", { token: tokenA });
  expect(rUser.status).toBe(403);
  const rAnon = await api(request, "GET", "/api/admin/logs?limit=10");
  expect(rAnon.status).toBe(401);
});

test("匿名可浏览社区 Feed（公开边界）", async ({ page }) => {
  await page.goto(FE + "/community");
  await expect(page.locator("body")).toContainText(/社区|帖子|动态/, { timeout: 20_000 });
});
