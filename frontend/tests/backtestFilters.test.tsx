import "./domSetup.mjs";
import React from "react";
import assert from "node:assert/strict";
import test, { afterEach } from "node:test";
import { render, fireEvent, cleanup } from "@testing-library/react";
import { BacktestFilterToggles } from "../src/components/strategy/BacktestFilterToggles";
import {
  buildFactorDetectRequest,
  buildStrategyBacktestRequest,
} from "../src/lib/backtestRequests";
import {
  defaultStrategyConfig,
  normalizeStrategyConfig,
  type StrategyProjectConfig,
} from "../src/lib/strategyStore";
import {
  applyDetectRunSnapshotToConfig,
  buildDetectRunUiSnapshot,
  defaultConfig,
  readDetectRunUiSnapshot,
} from "../src/lib/detectStore";
import { serializeYgFactorBody, serializeYgStrategyBody } from "../src/lib/ygApi";
import { configFromRunRequest } from "../src/lib/strategyLibraryApi";

afterEach(cleanup);

const FILTER_KEYS = [
  "filter_suspended",
  "filter_st",
  "filter_limit_up",
  "filter_limit_down",
] as const;

const LABELS = ["过滤停牌", "过滤ST", "过滤涨停", "过滤跌停"];

const EVENT_HINT = "事件模式由撮合层强制拦截，无需设置";

function allFilters(value: boolean) {
  return {
    filter_suspended: value,
    filter_st: value,
    filter_limit_up: value,
    filter_limit_down: value,
  };
}

function renderedCheckboxes(container: HTMLElement): HTMLInputElement[] {
  return Array.from(
    container.querySelectorAll("input[type=checkbox]"),
  ) as HTMLInputElement[];
}

// ---------- A. 组件与置灰 ----------

test("向量化模式：四个勾选框按固定顺序展示、默认不勾、均可点", () => {
  const view = render(
    <BacktestFilterToggles
      value={allFilters(false)}
      engineMode="vectorized"
      onChange={() => {}}
    />,
  );
  const inputs = renderedCheckboxes(view.container);

  assert.equal(inputs.length, 4);
  assert.deepEqual(
    inputs.map((i) => i.closest("label")?.textContent),
    LABELS,
  );
  assert.deepEqual(
    inputs.map((i) => i.disabled),
    [false, false, false, false],
  );
  assert.deepEqual(
    inputs.map((i) => i.checked),
    [false, false, false, false],
  );
});

test("点击各勾选框会把对应字段回传", () => {
  const patches: Array<Record<string, boolean>> = [];
  const view = render(
    <BacktestFilterToggles
      value={allFilters(false)}
      engineMode="vectorized"
      onChange={(p) => patches.push(p as Record<string, boolean>)}
    />,
  );

  for (const label of LABELS) {
    fireEvent.click(view.getByLabelText(label));
  }

  assert.deepEqual(
    patches,
    FILTER_KEYS.map((key) => ({ [key]: true })),
  );
});

test("事件模式：停牌/涨停/跌停置灰，ST 仍可勾，并给出提示", () => {
  const patches: Array<Record<string, boolean>> = [];
  const view = render(
    <BacktestFilterToggles
      value={allFilters(false)}
      engineMode="event"
      onChange={(p) => patches.push(p as Record<string, boolean>)}
    />,
  );

  assert.equal((view.getByLabelText("过滤停牌") as HTMLInputElement).disabled, true);
  assert.equal((view.getByLabelText("过滤涨停") as HTMLInputElement).disabled, true);
  assert.equal((view.getByLabelText("过滤跌停") as HTMLInputElement).disabled, true);
  assert.equal((view.getByLabelText("过滤ST") as HTMLInputElement).disabled, false);
  assert.equal(view.getAllByText(EVENT_HINT).length, 1);

  // 只有 ST 可交互。置灰的三个靠上面的 disabled 属性保证不可点——真实浏览器会
  // 抑制 disabled 控件的点击，而 jsdom 的 fireEvent.click 是直接派发事件、不模拟
  // 这一层，所以「点置灰项不回调」无法在此断言，不写成测试以免给出假保证。
  fireEvent.click(view.getByLabelText("过滤ST"));
  assert.deepEqual(patches, [{ filter_st: true }]);
});

test("事件模式：置灰的勾选框仍保留用户原有取值，切回向量化不丢设置", () => {
  const view = render(
    <BacktestFilterToggles
      value={allFilters(true)}
      engineMode="event"
      onChange={() => {}}
    />,
  );

  for (const label of LABELS) {
    assert.equal((view.getByLabelText(label) as HTMLInputElement).checked, true);
  }
});

// ---------- B. 配置登记（白名单回归） ----------

test("defaultStrategyConfig 四个过滤开关默认全关", () => {
  const cfg = defaultStrategyConfig();
  for (const key of FILTER_KEYS) {
    assert.equal(cfg[key], false, key);
  }
});

test("normalizeStrategyConfig 不丢弃四个过滤开关", () => {
  for (const key of FILTER_KEYS) {
    const raw: Partial<StrategyProjectConfig> = {};
    (raw as Record<string, boolean>)[key] = true;
    const cfg = normalizeStrategyConfig(raw);

    assert.equal(cfg[key], true, `${key} 被白名单丢弃`);
    for (const other of FILTER_KEYS) {
      if (other !== key) assert.equal(cfg[other], false, other);
    }
  }

  const empty = normalizeStrategyConfig({});
  for (const key of FILTER_KEYS) {
    assert.equal(empty[key], false, key);
  }
});

test("configFromRunRequest 还原过滤开关，老 run 回落 false", () => {
  const restored = configFromRunRequest({ filter_st: true, filter_limit_up: true });
  assert.equal(restored.filter_st, true);
  assert.equal(restored.filter_limit_up, true);
  assert.equal(restored.filter_suspended, false);
  assert.equal(restored.filter_limit_down, false);
});

// ---------- C. 因子侧快照往返 ----------

test("因子侧：四个过滤开关经快照往返后保持", () => {
  const cfg = {
    ...defaultConfig(["mom"]),
    filterSuspended: true,
    filterSt: true,
    filterLimitUp: true,
    filterLimitDown: true,
  };

  const snapshot = buildDetectRunUiSnapshot(cfg);
  const read = readDetectRunUiSnapshot({ _svquant_ui: snapshot });
  assert.ok(read, "快照应能被读回");
  assert.deepEqual(
    [read.filterSuspended, read.filterSt, read.filterLimitUp, read.filterLimitDown],
    [true, true, true, true],
  );

  const applied = applyDetectRunSnapshotToConfig(defaultConfig(["mom"]), read);
  assert.deepEqual(
    [
      applied.filterSuspended,
      applied.filterSt,
      applied.filterLimitUp,
      applied.filterLimitDown,
    ],
    [true, true, true, true],
  );
});

test("因子侧：老快照缺新字段时不报错且读回 false", () => {
  const legacy: Record<string, unknown> = {
    ...buildDetectRunUiSnapshot(defaultConfig(["mom"])),
  };
  delete legacy.filterSt;
  delete legacy.filterLimitDown;

  const read = readDetectRunUiSnapshot({ _svquant_ui: legacy });
  assert.ok(read, "老快照应仍可读回");
  assert.equal(read.filterSt, false);
  assert.equal(read.filterLimitDown, false);
  assert.equal(read.filterLimitUp, false);
});

// ---------- D. 请求体透传 ----------

test("序列化不剥离四个过滤字段", () => {
  // RE 的请求模型是 extra="forbid"，字段被吞掉会静默失去过滤、多发未知字段则 422。
  const strategyBody = serializeYgStrategyBody({
    strategy_id: "builtin",
    ...allFilters(true),
  });
  for (const key of FILTER_KEYS) {
    assert.equal(strategyBody[key], true, key);
  }

  const factorBody = serializeYgFactorBody({
    factor_name: "momentum",
    ...allFilters(true),
  });
  for (const key of FILTER_KEYS) {
    assert.equal(factorBody[key], true, key);
  }
});

test("因子检测请求体带上四个过滤开关", () => {
  const req = buildFactorDetectRequest(
    {
      ...defaultConfig([]),
      filterSuspended: true,
      filterSt: true,
      filterLimitUp: true,
      filterLimitDown: true,
    },
    { factor_name: "momentum" },
    { start: "2024-01-01", end: "2024-12-31" },
  );

  for (const key of FILTER_KEYS) {
    assert.equal(req[key], true, key);
  }
});

test("策略检测请求体带上四个过滤开关（两种引擎模式）", () => {
  for (const mode of ["vectorized", "event"] as const) {
    const req = buildStrategyBacktestRequest(
      {
        ...defaultStrategyConfig(),
        engine_mode: mode,
        ...allFilters(true),
      },
      {
        strategyId: "",
        snapshotCode: "class S: pass",
        range: { start: "2024-01-01", end: "2024-12-31" },
      },
    );

    for (const key of FILTER_KEYS) {
      assert.equal(req[key], true, `${mode}:${key}`);
    }
  }
});
