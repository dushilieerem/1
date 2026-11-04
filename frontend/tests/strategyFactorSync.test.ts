import "./domSetup.mjs";
import assert from "node:assert/strict";
import test, { afterEach } from "node:test";

import { clearFactorCache } from "../src/lib/factorCatalog";
import {
  buildCustomFactorStub,
  findUneditedFactorStub,
  resolveStrategyFactorBodies,
} from "../src/lib/strategyFactorSync";

Object.defineProperty(globalThis, "sessionStorage", {
  value: window.sessionStorage,
  configurable: true,
});

const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
  clearFactorCache();
  sessionStorage.clear();
});

function mockApi(opts: {
  builtin?: Array<{ name: string; library?: string }>;
  personal?: Array<Record<string, unknown>>;
  personalError?: boolean;
}) {
  globalThis.fetch = async (url) => {
    const path = new URL(String(url), "http://localhost").pathname;
    if (path === "/api/factor/re-catalog") {
      return Response.json({
        ok: true,
        factors: (opts.builtin || []).map((f) => ({
          name: f.name,
          library: f.library || "主因子库",
          description: f.name,
        })),
      });
    }
    if (path === "/api/factor/index") {
      return new Response("libraries: {}\n");
    }
    if (path === "/api/factor/libraries/factors") {
      if (opts.personalError) {
        return Response.json({ detail: "个人因子库加载失败" }, { status: 500 });
      }
      return Response.json({ factors: opts.personal || [] });
    }
    throw new Error(`Unexpected ${path}`);
  };
}

const personalRow = {
  id: 11,
  libraryId: 2,
  libraryName: "cx_quant_库",
  name: "cx_quant_ui_momentum_20",
  methodName: "cx_quant_ui_momentum_20",
  body: "def cx_quant_ui_momentum_20(self):\n    return self.close.pct_change(20)",
  description: "20 日动量",
  categoryLabel: "动量",
  formulaReady: true,
};

test("个人因子按真实源码同步，不再变成零值 stub", async () => {
  mockApi({ personal: [personalRow] });

  const bodies = await resolveStrategyFactorBodies(["cx_quant_ui_momentum_20"]);

  assert.match(bodies, /def cx_quant_ui_momentum_20\(self\):/);
  assert.match(bodies, /return self\.close\.pct_change\(20\)/);
  assert.doesNotMatch(bodies, /pct_change\(20\) \* 0/);
  assert.match(bodies, /@factor/);
});

test("个人因子没有公式时明确失败", async () => {
  mockApi({ personal: [{ ...personalRow, body: "", formulaReady: false }] });

  await assert.rejects(
    () => resolveStrategyFactorBodies(["cx_quant_ui_momentum_20"]),
    /尚未填写公式/,
  );
});

test("目录里没有且代码里没有实现的因子明确失败，不生成零值 stub", async () => {
  mockApi({ personal: [] });

  await assert.rejects(
    () => resolveStrategyFactorBodies(["unknown_factor"]),
    /不在内置\/个人因子目录/,
  );
});

test("同名内置/个人因子拒绝猜测源码", async () => {
  mockApi({
    builtin: [{ name: "cx_quant_ui_momentum_20" }],
    personal: [personalRow],
  });

  await assert.rejects(
    () => resolveStrategyFactorBodies(["cx_quant_ui_momentum_20"]),
    /名称冲突/,
  );
});

test("真正新增的临时因子可生成草稿，但未编辑占位会被识别", async () => {
  mockApi({ personal: [] });
  const stub = buildCustomFactorStub("my_temp", "临时动量");

  assert.equal(findUneditedFactorStub(stub), "my_temp");
  assert.equal(
    findUneditedFactorStub(stub.replace("pct_change(20) * 0  # TODO", "pct_change(10)")),
    null,
  );

  const bodies = await resolveStrategyFactorBodies(["my_temp"], {
    tempLabels: { my_temp: "临时动量" },
  });
  assert.match(bodies, /# TODO/);
  assert.equal(findUneditedFactorStub(bodies), "my_temp");
});
