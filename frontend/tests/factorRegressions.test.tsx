import "./domSetup.mjs";
import React from "react";
import assert from "node:assert/strict";
import test, { afterEach } from "node:test";
import { render, fireEvent, cleanup, waitFor, act } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { EditorView } from "@codemirror/view";
import { FactorDetectPage } from "../src/pages/FactorDetectPage";
import { FactorDashboardPage } from "../src/pages/FactorDashboardPage";
import { UserFactorEditDialog } from "../src/components/UserFactorEditDialog";
import { sourceFromRequest, sourceRequestParts } from "../src/lib/detectSource";
import { buildDetectRunUiSnapshot, applyDetectRunSnapshotToConfig, readDetectRunUiSnapshot, defaultConfig } from "../src/lib/detectStore";
import { userLibraryFactorToMeta } from "../src/lib/userFactorLibraries";

Object.defineProperty(globalThis, "sessionStorage", { value: window.sessionStorage, configurable: true });
window.requestAnimationFrame = (fn) => window.setTimeout(() => fn(0), 0);
window.cancelAnimationFrame = window.clearTimeout;
Object.defineProperty(globalThis, "Window", { value: window.constructor, configurable: true });
Object.defineProperty(globalThis, "getComputedStyle", { value: window.getComputedStyle.bind(window), configurable: true });
window.Range.prototype.getClientRects = () => [] as any;
window.Range.prototype.getBoundingClientRect = () => ({ top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0 }) as any;
const originalFetch = globalThis.fetch;
afterEach(() => { cleanup(); globalThis.fetch = originalFetch; });

const row = { id: 3, libraryId: 2, libraryName: "测试", name: "old_factor", body: "def old_factor(self):\n    return self.close.pct_change(5)", description: "原说明", categoryLabel: "其他", formulaReady: true };
const factor = userLibraryFactorToMeta(row as any);

test("FT-007: 编辑名称/说明/公式完整提交，取消不发请求", async () => {
  const sent: any[] = [];
  globalThis.fetch = async (url, init) => {
    sent.push({ url, body: JSON.parse(String(init?.body)) });
    return Response.json({ factor: { ...row, ...sent.at(-1).body } });
  };
  let saved: any;
  let closed = false;
  const view = render(<UserFactorEditDialog factor={factor} onSaved={f => { saved = f; }} onClose={() => { closed = true; }} />);
  fireEvent.change(view.getByLabelText("因子代码名"), { target: { value: "new_factor" } });
  fireEvent.change(view.getByLabelText("因子说明"), { target: { value: "新说明" } });
  fireEvent.change(view.getByLabelText("因子代码"), { target: { value: row.body.replace("(5)", "(10)") } });
  fireEvent.click(view.getByText("取消"));
  assert.equal(closed, true);
  assert.equal(sent.length, 0);
  fireEvent.click(view.getByText("保存"));
  await waitFor(() => assert.equal(saved?.name, "new_factor"));
  assert.equal(sent[0].url, "/api/factor/libraries/2/factors/3");
  assert.equal(sent[0].body.description, "新说明");
  assert.equal(sent[0].body.body, "def new_factor(self):\n    return self.close.pct_change(10)");
});

test("FT-007: 保存失败保留编辑内容并显示错误", async () => {
  globalThis.fetch = async () => Response.json({ detail: "你已有同名因子" }, { status: 400 });
  const view = render(<UserFactorEditDialog factor={factor} onSaved={() => assert.fail()} onClose={() => {}} />);
  fireEvent.change(view.getByLabelText("因子代码名"), { target: { value: "duplicate" } });
  fireEvent.click(view.getByText("保存"));
  await waitFor(() => assert.match(view.getByRole("alert").textContent!, /同名/));
  assert.equal((view.getByLabelText("因子代码名") as HTMLInputElement).value, "duplicate");
});

test("FT-011: 明确清空不回退为旧代码；空代码和注释拒绝执行", () => {
  for (const code of ["", "   \n", "# 无代码"]) {
    const cfg = { ...defaultConfig(["factor"]), source: { code, name: "factor" } };
    const snap = readDetectRunUiSnapshot({ _svquant_ui: buildDetectRunUiSnapshot(cfg) })!;
    const restored = applyDetectRunSnapshotToConfig(defaultConfig(["factor"]), snap);
    assert.equal(restored.source?.code, code);
    assert.throws(() => sourceRequestParts(restored.source!));
  }
});

test("FT-012/013: 历史执行源码还原100000，不依赖当前/已删除因子库", () => {
  const req = { factor_name: "old_factor", factor_code: row.body.replace("(5)", "(100000)") };
  const source = sourceFromRequest(JSON.parse(JSON.stringify(req)))!;
  assert.deepEqual(sourceRequestParts(source), req);
  assert.match(source.code, /100000/);
  assert.doesNotMatch(source.code, /self.old_factor\(/);
  assert.deepEqual(sourceRequestParts({ ...source, library: ["classic_indicators"] }).library_name, ["classic_indicators"]);
  assert.equal(sourceFromRequest({ factor_name: "SV01_0001", library_name: "classic_indicators" }), undefined);
});

let projectSeq = 0;
async function detectPage(deleted = false, historyCode?: string) {
  sessionStorage.setItem("svquant_user", JSON.stringify({ id: 77, username: "test" }));
  const id = `project-${++projectSeq}`;
  let project: any = { id, name: "test", factorName: row.name, description: "test", createdAt: "", updatedAt: "", runCount: 0, config: defaultConfig([row.name]) };
  const sent: Array<{ path: string; method: string; body: any }> = [];
  globalThis.fetch = async (url, init) => {
    const path = new URL(String(url), "http://localhost").pathname;
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    const method = init?.method || "GET";
    sent.push({ path, method, body });
    if (path === `/api/detect/projects/${id}`) {
      if (method === "PUT") project = structuredClone(body);
      return Response.json({ project });
    }
    if (path.endsWith(`/projects/${id}/runs`)) return Response.json({ runs: [] });
    if (path === "/api/detect/runs/history") return Response.json({ run: { id: "history", projectId: id, request: { factor_name: row.name, factor_code: historyCode, _svquant_ui: buildDetectRunUiSnapshot(project.config) }, factorName: row.name } });
    if (path === "/api/factor/re-catalog") return Response.json({ factors: [] });
    if (path === "/api/factor/index") return new Response("libraries: {}");
    if (path === "/api/factor/libraries/factors") return Response.json({ factors: deleted ? [] : [row] });
    if (path === "/api/factor/libraries/2/factors/3") return Response.json({ factor: { ...row, ...body } });
    if (path === "/api/backtest/factor") return Response.json({ metrics: {}, error: "测试桩停止于计算入口" });
    throw new Error(`Unexpected request ${method} ${path}`);
  };
  const mount = () => render(<MemoryRouter initialEntries={[`/factor/detect/${id}${historyCode ? "?runId=history" : ""}`]}><Routes><Route path="/factor/detect/:projectId" element={<FactorDetectPage />} /></Routes></MemoryRouter>);
  const view = mount();
  await waitFor(() => assert.ok(view.container.querySelector(".cm-editor")), { timeout: 15000 });
  const editor = () => EditorView.findFromDOM(document.querySelector(".cm-editor") as HTMLElement)!;
  return { view, editor, sent, mount, project: () => project };
}

test("FT-007/011 页面回归：修改保存重开仍为新公式，清空后点击检测不发送任务", async () => {
  const page = await detectPage();
  const source = row.body.replace("(5)", "(10)");
  await act(async () => page.editor().dispatch({ changes: { from: 0, to: page.editor().state.doc.length, insert: source } }));
  fireEvent.click(page.view.getByRole("button", { name: "保存" }));
  await waitFor(() => assert.equal(page.project().config.source?.code, source));
  assert.ok(page.sent.some((r) => r.path === "/api/factor/libraries/2/factors/3" && r.body.body === source));
  page.view.unmount();
  const reopened = page.mount();
  await waitFor(() => assert.equal(page.editor().state.doc.toString(), source));
  await act(async () => page.editor().dispatch({ changes: { from: 0, to: page.editor().state.doc.length, insert: "" } }));
  fireEvent.click(reopened.getByRole("button", { name: "进行检测" }));
  await waitFor(() => assert.match(reopened.container.textContent!, /因子代码不能为空/));
  assert.equal(page.sent.filter((r) => r.path === "/api/backtest/factor").length, 0);
});

test("FT-013 页面回归：因子已删除仍提交历史原文，不生成递归调用", async () => {
  const source = row.body.replace("(5)", "(100000)");
  const page = await detectPage(true, source);
  await waitFor(() => assert.equal(page.editor().state.doc.toString(), source));
  fireEvent.click(page.view.getByRole("button", { name: "进行检测" }));
  await waitFor(() => assert.equal(page.sent.filter((r) => r.path === "/api/backtest/factor").length, 1));
  assert.equal(page.sent.find((r) => r.path === "/api/backtest/factor")!.body.factor_code, source);
});

test("FT-013 页面回归：已删除且没有代码快照时明确阻止重跑", async () => {
  const page = await detectPage(true);
  fireEvent.click(page.view.getByRole("button", { name: "进行检测" }));
  await waitFor(() => assert.match(page.view.container.textContent!, /已删除或不可用/));
  assert.equal(page.sent.filter((r) => r.path === "/api/backtest/factor").length, 0);
});

// —— 因子面板（/factor/dashboard）——
// 回归背景：RE 内置库重组为单库「主因子库」后，页面的分类 Tab 曾退化成
// 只有「全部/主因子库」，且刷新入口在产品上不可达。

const DASH_FACTORS = [
  { name: "SV01_0001", library: "主因子库", description: "长问句A", display_name: "涨跌日频率差", category_label: "动量因子" },
  { name: "SV08_0001", library: "主因子库", description: "长问句B", display_name: "量价背离度", category_label: "量价关系因子" },
];

const DASH_ROWS = [
  { factor_name: "SV01_0001", name_cn: "涨跌日频率差", library: "主因子库", category_label: "动量因子", ic_mean: 2.06, rank_ic: 3.09 },
  { factor_name: "SV08_0001", name_cn: "量价背离度", library: "主因子库", category_label: "量价关系因子", ic_mean: 1.11 },
];

function mountDashboard(role: string, rows: any[] = DASH_ROWS) {
  sessionStorage.setItem("svquant_user", JSON.stringify({ id: 9, username: "u", role, status: "active" }));
  const sent: Array<{ path: string; method: string; body: any }> = [];
  globalThis.fetch = async (url, init) => {
    const path = new URL(String(url), "http://localhost").pathname;
    const method = init?.method || "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    sent.push({ path, method, body });
    if (path === "/api/factor/re-catalog") return Response.json({ ok: true, factors: DASH_FACTORS });
    if (path === "/api/factor/index") return new Response("libraries: {}");
    if (path === "/api/factor/dashboard") {
      return Response.json({ rows, job: { status: "idle" }, verify_summary: { pending: 2, passed: 0, failed: 0 } });
    }
    if (path === "/api/factor/dashboard/refresh") return Response.json({ ok: true, job: { status: "running", done: 0, total: 2 } });
    if (path === "/api/factor/dashboard/status") return Response.json({ status: "done" });
    throw new Error(`Unexpected request ${method} ${path}`);
  };
  const view = render(<MemoryRouter><FactorDashboardPage /></MemoryRouter>);
  return { view, sent };
}

test("面板点击IC升降序，缺失值均排在有效值之后，负数与0正常排序", async () => {
  const { view } = mountDashboard("user", [
    { factor_name: "missing", name_cn: "缺失IC", ic_mean: null },
    { factor_name: "negative", name_cn: "负IC", ic_mean: -2 },
    { factor_name: "zero", name_cn: "零IC", ic_mean: 0 },
  ]);
  await waitFor(() => assert.ok(view.getByText("缺失IC")));
  const names = () => [...view.container.querySelectorAll("tbody tr")].map(r => r.querySelector("code")?.textContent);
  assert.deepEqual(names(), ["zero", "negative", "missing"]);
  fireEvent.click(view.getByRole("columnheader", { name: "IC均值" }));
  assert.deepEqual(names(), ["negative", "zero", "missing"]);
  fireEvent.click(view.getByRole("columnheader", { name: "IC均值" }));
  assert.deepEqual(names(), ["zero", "negative", "missing"]);
});

test("因子面板：分类 Tab 取 RE 目录的分类，不再退化成单一库名", async () => {
  const { view } = mountDashboard("user");
  await waitFor(() => assert.ok(view.getByRole("button", { name: "动量因子" })));
  assert.ok(view.getByRole("button", { name: "量价关系因子" }));
  assert.equal(view.queryByRole("button", { name: "主因子库" }), null);
  // 子类列显示真实分类，而非恒为「主因子库」
  await waitFor(() => assert.ok(view.getByText("涨跌日频率差")));
});

test("因子面板：选分类只做本地过滤，不重新拉取", async () => {
  const { view, sent } = mountDashboard("user");
  await waitFor(() => assert.ok(view.getByText("量价背离度")));
  const before = sent.filter((r) => r.path === "/api/factor/dashboard").length;
  fireEvent.click(view.getByRole("button", { name: "动量因子" }));
  await waitFor(() => assert.equal(view.queryByText("量价背离度"), null));
  assert.ok(view.getByText("涨跌日频率差"));
  assert.equal(sent.filter((r) => r.path === "/api/factor/dashboard").length, before);
});

/** jsdom 的 confirm 恒为假，按需打桩；返回还原函数 */
function stubConfirm(result: boolean): () => void {
  const original = window.confirm;
  window.confirm = () => result;
  return () => {
    window.confirm = original;
  };
}

test("因子面板：刷新指标按钮仅管理员可见，确认后才提交整批重算", async () => {
  const admin = mountDashboard("admin");
  const refreshReqs = () => admin.sent.filter((r) => r.path === "/api/factor/dashboard/refresh");
  await waitFor(() => assert.ok(admin.view.getByRole("button", { name: /刷新指标/ })));

  // 取消确认：不发请求（整轮数十分钟，必须给人反悔的机会）
  const restoreCancel = stubConfirm(false);
  fireEvent.click(admin.view.getByRole("button", { name: /刷新指标/ }));
  await new Promise((r) => setTimeout(r, 30));
  assert.equal(refreshReqs().length, 0);
  restoreCancel();

  // 确认：提交，且 skip_ok=false —— 重新计算，否则行情更新后指标永远不变
  const restoreOk = stubConfirm(true);
  fireEvent.click(admin.view.getByRole("button", { name: /刷新指标/ }));
  await waitFor(() => {
    const req = refreshReqs()[0];
    assert.ok(req);
    assert.equal(req!.method, "POST");
    assert.equal(req!.body.universe, "CSI300");
    assert.equal(req!.body.period, "3y");
    assert.equal(req!.body.filter_limit_up, true);
    assert.equal(req!.body.skip_ok, false);
  });
  restoreOk();
  cleanup();

  const plain = mountDashboard("user");
  await waitFor(() => assert.ok(plain.view.getByText("因子表现总览")));
  assert.equal(plain.view.queryByRole("button", { name: /刷新指标/ }), null);
});
