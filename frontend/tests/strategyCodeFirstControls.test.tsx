import "./domSetup.mjs";
import React from "react";
import assert from "node:assert/strict";
import test, { afterEach } from "node:test";
import { render, cleanup, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ConfirmProvider } from "../src/components/ConfirmDialog";
import { StrategyBacktestPage } from "../src/pages/StrategyBacktestPage";
import { defaultStrategyConfig } from "../src/lib/strategyStore";

Object.defineProperty(globalThis, "sessionStorage", {
  value: window.sessionStorage,
  configurable: true,
});
window.requestAnimationFrame = (fn) => window.setTimeout(() => fn(0), 0);
window.cancelAnimationFrame = window.clearTimeout;
Object.defineProperty(globalThis, "Window", {
  value: window.constructor,
  configurable: true,
});
Object.defineProperty(globalThis, "getComputedStyle", {
  value: window.getComputedStyle.bind(window),
  configurable: true,
});
window.Range.prototype.getClientRects = () => [] as any;
window.Range.prototype.getBoundingClientRect = () =>
  ({ top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0 }) as any;

const FREE_CODE = `import pandas as pd

class FreeStrategy:
    def __init__(self, close):
        self.close = close

    def generate_signals(self):
        return pd.DataFrame(0.0, index=self.close.index, columns=self.close.columns)
`;

const originalFetch = globalThis.fetch;
afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
  sessionStorage.clear();
});

function mockProject(code: string) {
  sessionStorage.setItem(
    "svquant_user",
    JSON.stringify({ id: 8801, username: "strategy_controls" }),
  );
  const cfg = { ...defaultStrategyConfig(), strategy_code: code };
  const project = {
    id: "q-controls",
    name: "控件边界",
    description: "",
    createdAt: "",
    updatedAt: "",
    runCount: 0,
    config: cfg,
  };
  globalThis.fetch = async (url) => {
    const path = new URL(String(url), "http://localhost").pathname;
    if (path === "/api/strategy/projects/q-controls") return Response.json({ project });
    if (path === "/api/factor/re-catalog") return Response.json({ ok: true, factors: [] });
    if (path === "/api/factor/index") return new Response("libraries: {}\n");
    if (path === "/api/factor/libraries/factors") return Response.json({ factors: [] });
    throw new Error(`Unexpected ${path}`);
  };
}

function renderPage() {
  return render(
    <ConfirmProvider>
      <MemoryRouter initialEntries={["/strategy/research/q-controls"]}>
        <Routes>
          <Route path="/strategy/research/:projectId" element={<StrategyBacktestPage />} />
        </Routes>
      </MemoryRouter>
    </ConfirmProvider>,
  );
}

test("generate_signals 自由策略隐藏不生效的持仓数/调仓周期表单", async () => {
  mockProject(FREE_CODE);
  const view = renderPage();

  await waitFor(() => assert.ok(view.container.querySelector(".cm-editor")), { timeout: 15000 });
  assert.equal(view.queryByText("持仓数"), null);
  assert.equal(view.queryByText("调仓周期（交易日）"), null);
  assert.match(
    view.getByText(/持仓数、调仓周期由代码内常量控制/).textContent || "",
    /已隐藏/,
  );
});

test("FactorPortfolio 策略保留持仓数/调仓周期表单", async () => {
  mockProject(defaultStrategyConfig().strategy_code);
  const view = renderPage();

  await waitFor(() => assert.ok(view.container.querySelector(".cm-editor")), { timeout: 15000 });
  assert.ok(view.getByText("持仓数"));
  assert.ok(view.getByText("调仓周期（交易日）"));
});
