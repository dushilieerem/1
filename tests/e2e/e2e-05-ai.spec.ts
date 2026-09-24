import { test, expect } from "@playwright/test";
import {
  FE, USER_A, PW,
  api, registerUser, loginUser, loginUi, noSecretLeak,
} from "./helpers/r5";

/**
 * E2E-04(设计编号) AI 对话与流水线（用户流程五：AI Agent 流程）
 * 关联用例：TC-AI-001/004/006/011/014/017/020、TC-AI-SEC-ANON
 * 口径：验证接口成功与异常处理，不评模型质量、不消耗真实 LLM 费用。
 */

let tokenA = "";
let tokenAdmin = "";

test.beforeAll(async ({ request }) => {
  tokenA = (await registerUser(request, USER_A, PW)).token;
});

test("AI 对话页加载且输入区可用（UI，登录态）", async ({ page }) => {
  await loginUi(page, USER_A, PW);
  await page.goto(FE + "/ai/chat");
  await expect(page.locator('textarea[placeholder*="向 SV 助手提问"]')).toBeVisible({ timeout: 20_000 });
});

test("模型列表接口与页面元数据（API）", async ({ request }) => {
  const r = await api(request, "GET", "/api/ai/chat/models", { token: tokenA });
  expect(r.status).toBe(200);
  expect(noSecretLeak(r.json)).toBeTruthy();
  // 模型列表结构：数组或含 items/models 字段，允许空（未配置供应商时的降级口径）
  const models = Array.isArray(r.json) ? r.json : r.json?.models || r.json?.items || [];
  expect(Array.isArray(models)).toBeTruthy();
});

test("匿名 AI 对话被拒（401）", async ({ request }) => {
  const r = await api(request, "POST", "/api/ai/chat", { body: { messages: [{ role: "user", content: "hi" }] } });
  expect(r.status).toBe(401);
});

test("AI 对话错误路径：无效模型返回映射错误且无敏感信息（API，不消耗费用）", async ({ request }) => {
  const r = await api(request, "POST", "/api/ai/chat", {
    token: tokenA,
    body: { model: "r5_no_such_model__", messages: [{ role: "user", content: "ping" }] },
  });
  expect(r.status).toBeGreaterThanOrEqual(400);
  expect(r.status).toBeLessThan(600);
  expect(noSecretLeak(r.json)).toBeTruthy();
});

test("Agent 用量与额度（API）", async ({ request }) => {
  const usage = await api(request, "GET", "/api/agent/usage/me?days=1", { token: tokenA });
  expect(usage.status).toBe(200);

  // 管理员可设置额度；普通用户设置额度被拒
  const tokenAdmin = (await loginUser(request, process.env.R5_ADMIN_USER || "admin", process.env.R5_ADMIN_PASSWORD || "admin123")).token;
  const rAdminUsage = await api(request, "GET", "/api/agent/usage?days=1", { token: tokenAdmin });
  expect(rAdminUsage.status).toBe(200);
  const me = await api(request, "GET", "/api/auth/me", { token: tokenA });
  const userId = me.json?.user?.id;
  expect(userId).toBeTruthy();
  const rAdminSet = await api(request, "POST", "/api/agent/usage/quota", { token: tokenAdmin, body: { user_id: userId, quota_daily: 10 } });
  expect(rAdminSet.status).toBe(200);
  const rUserSet = await api(request, "POST", "/api/agent/usage/quota", { token: tokenA, body: { user_id: userId, quota_daily: 10 } });
  expect(rUserSet.status).toBe(403);
});

test("Agent Run 非法 skills 被拒（API 参数校验）", async ({ request }) => {
  const r = await api(request, "POST", "/api/agent/runs", { token: tokenA, body: { goal: "R5 invalid skills", skills: "bad" } });
  expect(r.status).toBe(400);
});
