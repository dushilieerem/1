import "./domSetup.mjs";
import React from "react";
import assert from "node:assert/strict";
import test, { afterEach } from "node:test";
import { render, fireEvent, cleanup, waitFor, act } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { EditorView } from "@codemirror/view";
import { FactorDetectPage } from "../src/pages/FactorDetectPage";
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
  await waitFor(() => assert.ok(view.container.querySelector(".cm-editor")));
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
