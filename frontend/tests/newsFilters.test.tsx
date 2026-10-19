import "./domSetup.mjs";
import React from "react";
import assert from "node:assert/strict";
import test, { afterEach } from "node:test";
import { cleanup, fireEvent, render, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { NewsPage } from "../src/pages/NewsPage";

Object.defineProperty(globalThis, "sessionStorage", { value: window.sessionStorage, configurable: true });
const originalFetch = globalThis.fetch;
const sample = {
  id: 1, title: "港股军工测试资讯", summary: "测试摘要", body: "",
  publishedAt: "2026-10-19T10:00:00+08:00", source: "cls", sourceLabel: "财联社",
  category: "flash", url: "", symbols: [], themes: ["港股", "A股"],
  industries: ["计算机", "机械设备", "国防军工"], isFlash: true, isFeatured: false,
};

function setup(selectedIndustries: string[] = []) {
  const requests: URL[] = [];
  sessionStorage.setItem("svquant.news.ui.v3", JSON.stringify({ industries: selectedIndustries }));
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    const data = url.pathname === "/api/news/dict"
      ? { themes: ["港股", "A股"], industries: ["计算机", "机械设备", "国防军工"] }
      : { items: [sample], total: 1 };
    if (url.pathname === "/api/news") requests.push(url);
    return new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  const view = render(<MemoryRouter><NewsPage /></MemoryRouter>);
  return { view, requests };
}

afterEach(() => { cleanup(); sessionStorage.clear(); globalThis.fetch = originalFetch; });

test("所选行业排在第三项时仍在结果卡片展示，避免看起来只命中港股", async () => {
  const { view } = setup(["国防军工"]);
  const main = within(view.getByRole("main"));
  await waitFor(() => assert.ok(main.getByRole("button", { name: "国防军工", exact: true })));
  assert.ok(main.getByRole("button", { name: "港股", exact: true }));
  assert.ok(view.getByText("标签筛选（同时满足所有已选标签）"));
});

test("没有选中行业时保留原来的两项简略展示", async () => {
  const { view } = setup();
  const main = within(view.getByRole("main"));
  await waitFor(() => assert.ok(main.getByRole("button", { name: "计算机", exact: true })));
  assert.ok(main.getByRole("button", { name: "机械设备", exact: true }));
  assert.equal(main.queryByRole("button", { name: "国防军工", exact: true }), null);
});

test("多选及取消标签时完整发送剩余条件，不丢失其他维度", async () => {
  const { view, requests } = setup();
  const main = within(view.getByRole("main"));
  await waitFor(() => assert.ok(main.getByRole("button", { name: "港股", exact: true })));
  fireEvent.click(main.getByRole("button", { name: "港股", exact: true }));
  fireEvent.click(main.getByRole("button", { name: "A股", exact: true }));
  fireEvent.click(view.getByRole("button", { name: "国防军工", exact: true }));
  await waitFor(() => {
    const last = requests.at(-1)!;
    assert.deepEqual(last.searchParams.getAll("theme"), ["港股", "A股"]);
    assert.deepEqual(last.searchParams.getAll("industry"), ["国防军工"]);
  });
  fireEvent.click(view.getByRole("button", { name: /题材.*港股.*×/ }));
  await waitFor(() => {
    const last = requests.at(-1)!;
    assert.deepEqual(last.searchParams.getAll("theme"), ["A股"]);
    assert.deepEqual(last.searchParams.getAll("industry"), ["国防军工"]);
  });
});
