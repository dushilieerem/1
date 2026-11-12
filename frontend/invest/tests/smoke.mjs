import assert from "node:assert/strict";
import { chromium } from "playwright";

const base = process.env.INVEST_H5_URL || "http://127.0.0.1:9540";
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push(String(e)));

try {
  await page.goto(`${base}/`, { waitUntil: "networkidle" });
  if (await page.getByRole("button", { name: /进入 Invest/ }).count()) {
    await page.getByRole("button", { name: /进入 Invest/ }).click();
  }
  await page.waitForTimeout(700);
  assert.match(await page.locator("body").innerText(), /今日概览/);

  await page.locator(".stock-row").filter({ hasText: "宁德时代" }).first().click();
  await page.waitForTimeout(700);
  assert.match(await page.locator("body").innerText(), /数据摘要/);
  await page.locator(".seg.period-seg button", { hasText: "周K" }).click();
  await page.waitForTimeout(600);
  await page.locator(".seg.stock-seg button", { hasText: "财务" }).click();
  await page.waitForTimeout(300);
  assert.match(await page.locator("body").innerText(), /财务趋势/);

  await page.goto(`${base}/topic/ai`, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  assert.match(await page.locator("body").innerText(), /历史/);
  assert.match(await page.locator("body").innerText(), /base rate|历史分布|未来 20 日/);

  await page.goto(`${base}/portfolio`, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  assert.match(await page.locator("body").innerText(), /诊断报告/);
  assert.match(await page.locator("body").innerText(), /配置偏离/);

  await page.goto(`${base}/watch`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  assert.match(await page.locator("body").innerText(), /关注事件/);

  await page.goto(`${base}/news`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  assert.match(await page.locator("body").innerText(), /全部/);
  assert.match(await page.locator("body").innerText(), /要闻|公告|研报/);

  await page.goto(`${base}/search`, { waitUntil: "networkidle" });
  await page.locator(".search-input input").fill("宁德");
  await page.waitForTimeout(700);
  assert.match(await page.locator("body").innerText(), /宁德时代/);

  await page.goto(`${base}/me`, { waitUntil: "networkidle" });
  await page.waitForTimeout(400);
  assert.match(await page.locator("body").innerText(), /数据与口径/);
  await page.locator("button", { hasText: "重新测评" }).click();
  await page.waitForTimeout(300);
  assert.equal(await page.evaluate(() => !!document.activeElement?.closest(".sheet")), true);
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  assert.equal(await page.locator(".sheet").count(), 0);

  const anon = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await anon.goto(`${base}/privacy`, { waitUntil: "networkidle" });
  assert.match(await anon.locator("body").innerText(), /隐私政策/);
  await anon.goto(`${base}/register`, { waitUntil: "networkidle" });
  assert.match(await anon.locator("body").innerText(), /创建账号/);
  await anon.close();

  assert.deepEqual(errors, [], `console errors: ${errors.join(" | ")}`);
  console.log("invest H5 smoke: OK");
} finally {
  await browser.close();
}
