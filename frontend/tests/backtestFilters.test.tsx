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
  DEFAULT_EXECUTION_TIMING,
  DETECT_GROUP_OPTIONS,
  EXECUTION_TIMING_OPTIONS,
  applyDetectRunSnapshotToConfig,
  buildDetectRunUiSnapshot,
  defaultConfig,
  normalizeDetectGroups,
  normalizeExecutionTiming,
  readDetectRunUiSnapshot,
} from "../src/lib/detectStore";
import { serializeYgFactorBody, serializeYgStrategyBody } from "../src/lib/ygApi";
import { configFromRunRequest } from "../src/lib/strategyLibraryApi";
import {
  RE_Q1_DIRECTION_HINT,
  groupLayerKeys,
  icUnavailableHint,
  portfolioConvention,
  quantileLabel,
} from "../src/lib/factorPanelLabels";

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

test("configFromRunRequest 还原 execution_timing，缺省/非法值回落 next_close", () => {
  for (const timing of ["next_open", "same_close", "next_close"] as const) {
    assert.equal(
      configFromRunRequest({ execution_timing: timing }).execution_timing,
      timing,
    );
  }
  assert.equal(configFromRunRequest({}).execution_timing, "next_close");
  assert.equal(
    configFromRunRequest({ execution_timing: "bad" as never }).execution_timing,
    "next_close",
  );
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

// ---------- E. 成交时点（execution_timing） ----------
//
// 与过滤开关同样的两类坑：配置白名单丢字段、老快照缺字段读回 undefined。
// 另外成交时点还多一个坑——switchEngineMode 重建 cfg 时要显式保留。

const EXECUTION_TIMINGS = EXECUTION_TIMING_OPTIONS.map((o) => o.code);

test("成交时点选项覆盖三种取值且默认是 next_close", () => {
  assert.deepEqual([...EXECUTION_TIMINGS], ["same_close", "next_close", "next_open"]);
  assert.equal(DEFAULT_EXECUTION_TIMING, "next_close");
});

test("normalizeExecutionTiming 收敛非法与缺失值", () => {
  for (const code of EXECUTION_TIMINGS) {
    assert.equal(normalizeExecutionTiming(code), code);
  }
  for (const bad of [undefined, null, "", "  ", "same_open", 42, {}]) {
    assert.equal(normalizeExecutionTiming(bad), "next_close", String(bad));
  }
});

test("策略配置默认 next_close，且白名单不丢弃该字段", () => {
  assert.equal(defaultStrategyConfig().execution_timing, "next_close");

  assert.equal(
    normalizeStrategyConfig({ execution_timing: "next_open" }).execution_timing,
    "next_open",
  );
  assert.equal(
    normalizeStrategyConfig({ execution_timing: "same_close" }).execution_timing,
    "same_close",
  );
  // 非法值回落默认，不能留 undefined —— RE 端 extra=forbid 会直接 422。
  assert.equal(
    normalizeStrategyConfig({ execution_timing: "bogus" as never }).execution_timing,
    "next_close",
  );
  assert.equal(normalizeStrategyConfig({}).execution_timing, "next_close");
});

test("因子侧默认 next_close，快照往返保持", () => {
  assert.equal(defaultConfig(["mom"]).executionTiming, "next_close");

  const snapshot = buildDetectRunUiSnapshot({
    ...defaultConfig(["mom"]),
    executionTiming: "next_open",
  });
  const read = readDetectRunUiSnapshot({ _svquant_ui: snapshot });
  assert.ok(read, "快照应能被读回");
  assert.equal(read.executionTiming, "next_open");

  const applied = applyDetectRunSnapshotToConfig(defaultConfig(["mom"]), read);
  assert.equal(applied.executionTiming, "next_open");
});

test("因子侧：老快照缺 executionTiming 时回落 next_close", () => {
  const legacy: Record<string, unknown> = {
    ...buildDetectRunUiSnapshot(defaultConfig(["mom"])),
  };
  delete legacy.executionTiming;

  const read = readDetectRunUiSnapshot({ _svquant_ui: legacy });
  assert.ok(read, "老快照应仍可读回");
  assert.equal(read.executionTiming, "next_close");
});

test("序列化不剥离 execution_timing", () => {
  const strategyBody = serializeYgStrategyBody({
    strategy_id: "builtin",
    execution_timing: "next_open",
  });
  assert.equal(strategyBody.execution_timing, "next_open");

  const factorBody = serializeYgFactorBody({
    factor_name: "momentum",
    execution_timing: "next_open",
  });
  assert.equal(factorBody.execution_timing, "next_open");
});

test("两个回测请求体都带上 execution_timing", () => {
  const factorReq = buildFactorDetectRequest(
    { ...defaultConfig([]), executionTiming: "same_close" },
    { factor_name: "momentum" },
    { start: "2024-01-01", end: "2024-12-31" },
  );
  assert.equal(factorReq.execution_timing, "same_close");

  for (const mode of ["vectorized", "event"] as const) {
    const strategyReq = buildStrategyBacktestRequest(
      { ...defaultStrategyConfig(), engine_mode: mode, execution_timing: "next_open" },
      {
        strategyId: "",
        snapshotCode: "class S: pass",
        range: { start: "2024-01-01", end: "2024-12-31" },
      },
    );
    assert.equal(strategyReq.execution_timing, "next_open", mode);
  }
});

test("因子检测请求体在 config 缺失时回落 next_close", () => {
  const cfg = defaultConfig([]);
  delete (cfg as { executionTiming?: unknown }).executionTiming;
  const req = buildFactorDetectRequest(
    cfg,
    { factor_name: "momentum" },
    { start: "2024-01-01", end: "2024-12-31" },
  );
  assert.equal(req.execution_timing, "next_close");
});

// ---------- F. 因子分组数 ----------
//
// RE 的约束是 2~10（groups = Field(5, ge=2, le=10)）。此前下拉里含「1 组」，
// 选了必然 422。这里把「选项必须落在 RE 允许区间内」固化成断言，避免再次跑偏。

const RE_GROUPS_MIN = 2;
const RE_GROUPS_MAX = 10;

test("因子分组选项全部落在 RE 允许的 2~10 内", () => {
  assert.ok(DETECT_GROUP_OPTIONS.length > 0);
  for (const n of DETECT_GROUP_OPTIONS) {
    assert.ok(n >= RE_GROUPS_MIN && n <= RE_GROUPS_MAX, `分组 ${n} 超出 RE 约束`);
  }
  assert.deepEqual([...DETECT_GROUP_OPTIONS], [3, 5, 10]);
});

test("normalizeDetectGroups 收敛越界与非法值", () => {
  for (const n of DETECT_GROUP_OPTIONS) {
    assert.equal(normalizeDetectGroups(n), n);
  }
  // 1 是这次修掉的越界值；2/4 不在选项里但 RE 允许，仍按默认收敛。
  for (const bad of [1, 0, -3, 2, 4, 6, 11, 999, NaN, null, undefined, "abc"]) {
    assert.equal(normalizeDetectGroups(bad), 5, String(bad));
  }
  assert.equal(normalizeDetectGroups("10"), 10, "字符串数字应被接受");
});

test("因子检测请求体不会发出越界的分组数", () => {
  for (const raw of [DETECT_GROUP_OPTIONS[0], DETECT_GROUP_OPTIONS[2], 1, 2, 11]) {
    const req = buildFactorDetectRequest(
      { ...defaultConfig([]), groups: raw },
      { factor_name: "momentum" },
      { start: "2024-01-01", end: "2024-12-31" },
    );
    const sent = Number(req.groups);
    assert.ok(
      sent >= RE_GROUPS_MIN && sent <= RE_GROUPS_MAX,
      `发出 ${sent}，超出 RE 约束`,
    );
  }
});

// ---------- G. IC 不可用原因（与计算失败区分） ----------
//
// RE 在 factor_analysis.definition.ic_unavailable_reason 给出原因；面板要据此
// 把「算成功但因子无区分度」与「计算失败」分开。老响应没有这个键。

test("icUnavailableHint 未给出原因时返回 null（不编造）", () => {
  for (const empty of [null, undefined, ""]) {
    assert.equal(icUnavailableHint(empty), null, String(empty));
  }
});

test("icUnavailableHint 覆盖 RE 的四种取值", () => {
  for (const reason of [
    "missing_inputs",
    "no_common_axis",
    "insufficient_cross_section",
    "zero_cross_sectional_variance",
  ]) {
    const hint = icUnavailableHint(reason);
    assert.ok(hint, reason);
    assert.ok(hint.includes("非计算失败"), `${reason}: ${hint}`);
    assert.ok(!hint.includes(reason), `${reason} 应被翻译成中文而不是原样透出`);
  }
});

test("icUnavailableHint 对未知取值原样透出，不吞掉", () => {
  const hint = icUnavailableHint("some_future_reason");
  assert.ok(hint);
  assert.ok(hint.includes("some_future_reason"), hint);
});

// ---------- H. 分位曲线不再截断到 5 条 + 方向口径文案 ----------
//
// 分组可选 3/5/10：旧实现写死 Math.min(groups, 5)，选 10 组时只画 Q1–Q5
// （十分位的上半段），同页的「分层区间收益」与分组表却全量展示 10 组。

test("groupLayerKeys 覆盖 2–10 组，不再截断到 5", () => {
  assert.deepEqual(groupLayerKeys(3), ["layer1", "layer2", "layer3"]);
  assert.equal(groupLayerKeys(5).length, 5);
  assert.equal(groupLayerKeys(10).length, 10);
  assert.equal(groupLayerKeys(10).at(-1), "layer10");
});

test("groupLayerKeys 对越界与脏值钳制，不抛错", () => {
  assert.deepEqual(groupLayerKeys(1), ["layer1", "layer2"]);
  assert.deepEqual(groupLayerKeys(99), groupLayerKeys(10));
  assert.deepEqual(groupLayerKeys(NaN), groupLayerKeys(5));
  assert.deepEqual(groupLayerKeys(undefined), groupLayerKeys(5));
});

test("quantileLabel 由层键给分位号，认不出时按序号回退", () => {
  assert.equal(quantileLabel("layer1", 0), "Q1");
  assert.equal(quantileLabel("layer10", 9), "Q10");
  assert.equal(quantileLabel("weird", 3), "Q4");
});

test("方向口径文案写明 Q1 = 因子值最大组", () => {
  assert.ok(RE_Q1_DIRECTION_HINT.includes("Q1"));
  assert.ok(RE_Q1_DIRECTION_HINT.includes("最大"));
});

test("组合口径文案区分纯多与多空，且都点名 Q1", () => {
  assert.ok(portfolioConvention("long_only").includes("Q1"));
  const short = portfolioConvention("long_short");
  assert.ok(short.includes("Q1") && short.includes("Q5") && short.includes("−"), short);
  // 认不出的组合类型不编造口径
  assert.equal(portfolioConvention("nonsense"), "");
  assert.equal(portfolioConvention(null), "");
});

test("多空口径使用本次报告的组数：3/5/10组分别对应Q3/Q5/Q10", () => {
  for (const groups of [3, 5, 10]) {
    assert.equal(portfolioConvention("long_short", groups),
      `多空 = Q1 − Q${groups}（做多最高组、做空最低组）`);
    assert.equal(portfolioConvention("long_only", groups), portfolioConvention("long_only"));
  }
});
