import { defineConfig } from "@playwright/test";

/**
 * R5 E2E 配置（SVQuant）。
 * - 单 worker 串行执行：测试数据带 R5_TEST_ 前缀，避免相互污染。
 * - 失败自动截图 + trace，证据复制到 docs/测试设计/evidence/<RUN_ID>/。
 * - 基址可用环境变量覆盖：R5_FE_BASE / R5_KH_BASE / R5_API_BASE。
 */
export default defineConfig({
  testDir: ".",
  timeout: 180_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["json", { outputFile: "test-results/r5-e2e-results.json" }]],
  outputDir: "test-results/artifacts",
  use: {
    headless: true,
    ignoreHTTPSErrors: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    actionTimeout: 20_000,
    navigationTimeout: 30_000,
  },
});
