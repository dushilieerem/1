import { test, expect } from "@playwright/test";
import { writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import {
  KH, RUN_ID, USER_A, PW, ADMIN_USER, ADMIN_PW,
  api, registerUser, loginUser, loginUi, noSecretLeak,
} from "./helpers/r5";

/**
 * E2E-05(设计编号) KnowledgeHub 完整链路（用户流程四）
 * 关联用例：TC-KH-003/004/005/011/012/019/021、TC-SEC-014/015
 * 载体：KH 独立前端（:9531）+ 主后端 /api/kh（进程内）。
 * KH ask 在无 LLM 依赖下返回可判定答案（R1 TC-KH-012 口径），不消耗真实 LLM 费用。
 */

let adminToken = "";
let userToken = "";
let collectionId = 0;
const COLL_NAME = `${RUN_ID}_khcoll`;
const NEEDLE = `R5_NEEDLE_${RUN_ID.replace(/\D/g, "").slice(-8)}`;

const FIXTURE_DIR = path.join(__dirname, "fixtures");
const MD_PATH = path.join(FIXTURE_DIR, "r5-kh-doc.md");

test.beforeAll(async ({ request }) => {
  mkdirSync(FIXTURE_DIR, { recursive: true });
  writeFileSync(
    MD_PATH,
    `# R5 E2E 文档\n\n关键词：${NEEDLE}\n\n这是 R5 端到端测试使用的知识库文档，用于验证上传、摄取与检索链路。\n`,
    "utf8",
  );
  adminToken = (await loginUser(request, ADMIN_USER, ADMIN_PW)).token;
  userToken = (await registerUser(request, USER_A, PW)).token;
});

test.afterAll(async ({ request }) => {
  if (collectionId) {
    await api(request, "DELETE", `/api/kh/collections/${collectionId}`, { token: adminToken });
  }
});

test("KH 管理员登录（UI，:9531）", async ({ page }) => {
  await page.goto(KH + "/login");
  const userInput = page.locator("input").first();
  await userInput.fill(ADMIN_USER);
  await page.locator('input[type="password"]').fill(ADMIN_PW);
  await page.getByRole("button", { name: "登录" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20_000 });
  await expect(page.locator("body")).toContainText(/知识库/, { timeout: 15_000 });
});

test("创建知识库集合（UI）并落库", async ({ page }) => {
  // KH 独立前端自带登录态（sessionStorage 隔离于 :9531），需在 KH 登录页登录
  await page.goto(KH + "/login");
  const userInput = page.locator("input").first();
  await userInput.fill(ADMIN_USER);
  await page.locator('input[type="password"]').fill(ADMIN_PW);
  await page.getByRole("button", { name: "登录" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20_000 });

  await page.goto(KH + "/datasets");
  await page.getByRole("button", { name: /创建知识库/ }).click();
  await page.getByPlaceholder("请输入名称").fill(COLL_NAME);
  await page.getByRole("button", { name: "保存" }).click();
  await page.waitForURL(/\/datasets\/\d+/, { timeout: 20_000 });
  collectionId = Number(page.url().match(/\/datasets\/(\d+)/)?.[1]);
  expect(collectionId).toBeTruthy();

  const list = await api(page.request, "GET", "/api/kh/collections", { token: adminToken });
  expect(list.status).toBe(200);
  expect(JSON.stringify(list.json)).toContain(COLL_NAME);
});

test("上传并摄取文档（UI setInputFiles → 自动 ingest）", async ({ page }) => {
  test.skip(!collectionId, "前置集合未创建");
  await page.goto(KH + "/login");
  const userInput = page.locator("input").first();
  await userInput.fill(ADMIN_USER);
  await page.locator('input[type="password"]').fill(ADMIN_PW);
  await page.getByRole("button", { name: "登录" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20_000 });
  await page.goto(`${KH}/datasets/${collectionId}`);

  await page.getByRole("button", { name: /新增文件|上传/ }).click();
  await page.setInputFiles('input[type="file"]', MD_PATH);
  await page.getByRole("button", { name: "保存" }).click();
  await expect(page.getByText("r5-kh-doc.md").first()).toBeVisible({ timeout: 30_000 });

  const docs = await api(page.request, "GET", `/api/kh/collections/${collectionId}/documents`, { token: adminToken });
  expect(docs.status).toBe(200);
  expect(JSON.stringify(docs.json)).toContain("r5-kh-doc.md");
});

test("检索命中测试关键词（API，含向量摄取依赖）", async ({ request }, testInfo) => {
  test.skip(!collectionId, "前置集合未创建");
  const r = await api(request, "POST", "/api/kh/search", {
    token: adminToken,
    body: { query: NEEDLE, collectionId, topK: 3 },
  });
  if (r.status !== 200) {
    testInfo.annotations.push({ type: "BLOCKED", description: `检索依赖摄取管线，HTTP ${r.status}` });
  }
  expect(r.status).toBe(200);
  expect(JSON.stringify(r.json)).toContain(NEEDLE.slice(0, 20));
});

test("KH ask 返回可判定答案（无 LLM 依赖口径）", async ({ request }) => {
  test.skip(!collectionId, "前置集合未创建");
  const r = await api(request, "POST", "/api/kh/ask", {
    token: adminToken,
    body: { query: `what is ${NEEDLE}?`, collectionIds: [collectionId], topK: 3 },
  });
  expect(r.status).toBe(200);
  expect(typeof r.json?.answer).toBe("string");
  expect(noSecretLeak(r.json)).toBeTruthy();
});

test("KH 权限：普通用户 403、匿名 401", async ({ request }) => {
  const rUser = await api(request, "GET", "/api/kh/collections", { token: userToken });
  expect([403, 404]).toContain(rUser.status);
  const rAnon = await api(request, "GET", "/api/kh/collections");
  expect(rAnon.status).toBe(401);
});

test("删除知识库集合（UI）并确认清理", async ({ page }) => {
  test.skip(!collectionId, "前置集合未创建");
  await page.goto(KH + "/login");
  const userInput = page.locator("input").first();
  await userInput.fill(ADMIN_USER);
  await page.locator('input[type="password"]').fill(ADMIN_PW);
  await page.getByRole("button", { name: "登录" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20_000 });

  await page.goto(KH + "/datasets");
  const card = page.locator("div").filter({ hasText: COLL_NAME }).last();
  await card.hover();
  await card.locator('button[title="删除"]').click();
  const confirm = page.locator("div").filter({ hasText: /确认删除|删除/ }).locator("visible=true").last();
  await confirm.getByRole("button", { name: /删除|确认|确定/ }).click();
  await expect(page.getByText(COLL_NAME)).toHaveCount(0, { timeout: 15_000 });

  collectionId = 0; // 已删除，afterAll 不再重复删除
  const list = await api(page.request, "GET", "/api/kh/collections", { token: adminToken });
  expect(JSON.stringify(list.json)).not.toContain(COLL_NAME);
});
