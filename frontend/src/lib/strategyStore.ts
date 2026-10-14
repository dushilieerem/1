import type { YgBacktestResponse, YgStrategyBacktestRequest } from "./ygApi";
import {
  authHeaders,
  assertAuthConsistency,
  getStoredUser,
  prepareAuthHandoff,
  subscribeAuth,
} from "./auth";
import {
  DEFAULT_EXECUTION_TIMING,
  DETECT_BENCHMARK_OPTIONS,
  DETECT_PERIOD_OPTIONS,
  DETECT_UNIVERSE_OPTIONS,
  EXECUTION_TIMING_OPTIONS,
  RE_MARKET_END,
  clampDateRange,
  defaultCustomRangeDates,
  normalizeExecutionTiming,
  periodToStartEnd,
  type ExecutionTiming,
  type RangeMode,
} from "./detectStore";
import {
  DEFAULT_STRATEGY_CODE,
  inferEngineModeFromCode,
  parseParamsFromCode,
  wrapBuiltinLibraryStrategy,
  wrapFactorCodeAsStrategy,
} from "./strategyCodeSync";
import type { StrategyWeightMode } from "./strategyFactorSync";
import type { YgStrategyEngineMode } from "./ygApi";

export type StrategyEngineMode = YgStrategyEngineMode;

export type StrategyProjectConfig = {
  universe: string;
  benchmark: string;
  rangeMode: RangeMode;
  backtestPeriod: string;
  startDate: string;
  endDate: string;
  commission_rate: number;
  stamp_tax: number;
  slippage_rate: number;
  initial_capital: number;
  top_n: number;
  rebalance_days: number;
  /** 回测请求：是否拉取 rebalance_logs */
  include_rebalance_logs: boolean;
  /** 回测请求：交易过滤开关（命名对齐 ResearchEngine 请求字段，默认全 false） */
  filter_suspended: boolean;
  filter_st: boolean;
  filter_limit_up: boolean;
  filter_limit_down: boolean;
  /** 成交时点，对标 RE execution_timing（默认 next_close） */
  execution_timing: ExecutionTiming;
  /** 执行模式：vectorized | event（对应 API engine_mode） */
  engine_mode: StrategyEngineMode;
  strategy_code: string;
  /** 信号因子积木 id（策略页左侧选择） */
  signal_factor_ids: string[];
  /** 与 signal_factor_ids 对齐的权重（百分比，合计约 100） */
  signal_factor_weights: number[];
  /** 赋幂相乘时的幂次 */
  signal_factor_powers: number[];
  /** 合成模式：赋权相加 / 赋幂相乘 / 自定义 */
  signal_weight_mode: StrategyWeightMode;
  /** 临时因子中文释义：方法名 → 释义（仅策略研究用） */
  signal_temp_labels?: Record<string, string>;
  /** 从平台策略库打开时：library:{id}，用于复用研究项目 */
  library_ref?: string;
  /** ResearchEngine 内置策略 ID；存在时由 RE 执行，研究页不展示源码 */
  strategy_id?: string;
};

export type StrategyProject = {
  id: string;
  name: string;
  description: string;
  createdAt: string;
  updatedAt: string;
  runCount: number;
  /** 系统预置样例，不可删除 */
  sample?: boolean;
  config: StrategyProjectConfig;
};

export type StrategyRunRecord = {
  id: string;
  projectId: string;
  name: string;
  description: string;
  remark?: string;
  flagged?: boolean;
  request: YgStrategyBacktestRequest;
  result: YgBacktestResponse;
  finishedAt: string;
  elapsedSec: number;
  /** 策略库入库快照：只读，不可改 */
  immutable?: boolean;
  sourceRunId?: string;
  libraryId?: number;
  libraryStrategyId?: number;
  libraryName?: string;
};

export const STRATEGY_UNIVERSE_OPTIONS = DETECT_UNIVERSE_OPTIONS;
export const STRATEGY_BENCHMARK_OPTIONS = DETECT_BENCHMARK_OPTIONS;
export const STRATEGY_PERIOD_OPTIONS = DETECT_PERIOD_OPTIONS;
export const STRATEGY_EXECUTION_TIMING_OPTIONS = EXECUTION_TIMING_OPTIONS;
export { RE_MARKET_END, periodToStartEnd, clampDateRange, defaultCustomRangeDates };

export function optionLabel(
  code: string,
  options: readonly { code: string; label: string }[],
): string {
  return options.find((o) => o.code === code)?.label || code || "—";
}

export function defaultStrategyConfig(): StrategyProjectConfig {
  const custom = defaultCustomRangeDates("10y");
  return {
    universe: "CSI500",
    benchmark: "CSI300",
    rangeMode: "period",
    backtestPeriod: "10y",
    startDate: custom.startDate,
    endDate: custom.endDate,
    commission_rate: 0.0003,
    stamp_tax: 0.001,
    slippage_rate: 0.001,
    initial_capital: 1_000_000,
    top_n: 30,
    rebalance_days: 20,
    include_rebalance_logs: true,
    filter_suspended: false,
    filter_st: false,
    filter_limit_up: false,
    filter_limit_down: false,
    execution_timing: DEFAULT_EXECUTION_TIMING,
    engine_mode: "vectorized",
    strategy_code: DEFAULT_STRATEGY_CODE,
    signal_factor_ids: [],
    signal_factor_weights: [],
    signal_factor_powers: [],
    signal_weight_mode: "sum",
    signal_temp_labels: {},
  };
}

/** 兼容旧项目缺字段 */
export function normalizeStrategyConfig(
  raw?: Partial<StrategyProjectConfig> | null,
): StrategyProjectConfig {
  const d = defaultStrategyConfig();
  const c = raw || {};
  const strategyId = c.strategy_id ? String(c.strategy_id).trim() : "";
  const isBuiltin = Boolean(strategyId);
  const strategyCode = (c.strategy_code || "").trim()
    ? String(c.strategy_code)
    : isBuiltin
      ? ""
      : d.strategy_code;
  return {
    universe: c.universe || d.universe,
    benchmark: c.benchmark || d.benchmark,
    rangeMode: c.rangeMode === "custom" ? "custom" : "period",
    backtestPeriod: c.backtestPeriod || d.backtestPeriod,
    startDate: c.startDate || d.startDate,
    endDate: c.endDate || d.endDate,
    commission_rate:
      typeof c.commission_rate === "number" ? c.commission_rate : d.commission_rate,
    stamp_tax: typeof c.stamp_tax === "number" ? c.stamp_tax : d.stamp_tax,
    slippage_rate:
      typeof c.slippage_rate === "number" ? c.slippage_rate : d.slippage_rate,
    initial_capital:
      typeof c.initial_capital === "number" ? c.initial_capital : d.initial_capital,
    top_n: typeof c.top_n === "number" && c.top_n > 0 ? c.top_n : d.top_n,
    rebalance_days:
      typeof c.rebalance_days === "number" && c.rebalance_days > 0
        ? c.rebalance_days
        : d.rebalance_days,
    include_rebalance_logs:
      typeof c.include_rebalance_logs === "boolean"
        ? c.include_rebalance_logs
        : d.include_rebalance_logs,
    // 注意：本函数是严格白名单，未在此列出的字段会在保存/加载项目时被丢弃。
    filter_suspended:
      typeof c.filter_suspended === "boolean"
        ? c.filter_suspended
        : d.filter_suspended,
    filter_st: typeof c.filter_st === "boolean" ? c.filter_st : d.filter_st,
    filter_limit_up:
      typeof c.filter_limit_up === "boolean"
        ? c.filter_limit_up
        : d.filter_limit_up,
    filter_limit_down:
      typeof c.filter_limit_down === "boolean"
        ? c.filter_limit_down
        : d.filter_limit_down,
    // 成交时点同样必须在白名单里，否则保存/加载项目时被静默丢弃。
    execution_timing: normalizeExecutionTiming(c.execution_timing),
    engine_mode:
      c.engine_mode === "event" || c.engine_mode === "vectorized"
        ? c.engine_mode
        : inferEngineModeFromCode(
            strategyCode || d.strategy_code,
          ),
    strategy_code: strategyCode,
    signal_factor_ids: Array.isArray(c.signal_factor_ids)
      ? c.signal_factor_ids.map(String).filter(Boolean)
      : d.signal_factor_ids,
    signal_factor_weights: Array.isArray(c.signal_factor_weights)
      ? c.signal_factor_weights.map((w) =>
          typeof w === "number" && Number.isFinite(w) ? w : 0,
        )
      : d.signal_factor_weights,
    signal_factor_powers: Array.isArray(c.signal_factor_powers)
      ? c.signal_factor_powers.map((p) =>
          typeof p === "number" && Number.isFinite(p) ? p : 1,
        )
      : d.signal_factor_powers,
    signal_weight_mode:
      c.signal_weight_mode === "product" || c.signal_weight_mode === "custom"
        ? c.signal_weight_mode
        : "sum",
    signal_temp_labels:
      c.signal_temp_labels && typeof c.signal_temp_labels === "object"
        ? Object.fromEntries(
            Object.entries(c.signal_temp_labels).map(([k, v]) => [
              String(k),
              String(v ?? ""),
            ]),
          )
        : {},
    library_ref: c.library_ref ? String(c.library_ref) : undefined,
    strategy_id: strategyId || undefined,
  };
}

export function resolveStrategyRange(cfg: StrategyProjectConfig): {
  start: string | null;
  end: string | null;
} {
  if (cfg.rangeMode === "custom") {
    return {
      start: cfg.startDate || null,
      end: cfg.endDate || null,
    };
  }
  const r = periodToStartEnd(cfg.backtestPeriod || "10y");
  return { start: r.start, end: r.end };
}

let projectCache: StrategyProject[] | null = null;

export function clearStrategyClientCache() {
  projectCache = null;
}

subscribeAuth(() => {
  clearStrategyClientCache();
});

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  assertAuthConsistency();
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers || {}),
    },
  });
  const text = await res.text();
  let data: T & { error?: string };
  try {
    data = JSON.parse(text) as T & { error?: string };
  } catch {
    throw new Error(res.ok ? "响应不是 JSON" : `HTTP ${res.status}`);
  }
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

export async function listStrategyProjects(opts?: {
  visible?: boolean;
}): Promise<StrategyProject[]> {
  const q = opts?.visible ? "?visible=1" : "";
  const data = await apiJson<{ projects: StrategyProject[] }>(
    `/api/strategy/projects${q}`,
  );
  projectCache = data.projects || [];
  return projectCache;
}

export async function listVisibleStrategyProjects(): Promise<StrategyProject[]> {
  // 恢复：列表展示全部项目（含尚未回测的新建 / 社区克隆）
  return listStrategyProjects();
}

export async function getStrategyProject(id: string): Promise<StrategyProject> {
  const data = await apiJson<{ project: StrategyProject }>(
    `/api/strategy/projects/${encodeURIComponent(id)}`,
  );
  return data.project;
}

export async function createStrategyProject(
  name: string,
  description?: string,
): Promise<StrategyProject> {
  const data = await apiJson<{ project: StrategyProject }>("/api/strategy/projects", {
    method: "POST",
    body: JSON.stringify({ name, description: description || name }),
  });
  clearStrategyClientCache();
  return data.project;
}

/** 从社区帖代码新建策略项目并写入可回测 strategy_code */
export async function createStrategyProjectFromCode(opts: {
  name: string;
  description?: string;
  strategyCode: string;
}): Promise<StrategyProject> {
  const { resolveStrategyCloneSource } = await import("./communityClone");
  const { parseLibrarySignalSelection } = await import("./strategyFactorSync");
  const { loadFactors } = await import("./factorCatalog");
  const raw = await resolveStrategyCloneSource(opts.strategyCode || "");
  const mode = inferEngineModeFromCode(raw);
  const code =
    mode === "event"
      ? wrapBuiltinLibraryStrategy(raw)
      : wrapFactorCodeAsStrategy(raw);
  const signal =
    mode === "event"
      ? { ids: [] as string[], weights: [] as number[], powers: [] as number[], weightMode: "sum" as const }
      : parseLibrarySignalSelection(code);
  const parsed = parseParamsFromCode(code);
  const catalog = await loadFactors(true).catch(() => []);
  const catalogNames = new Set<string>();
  for (const f of catalog) {
    catalogNames.add(f.name);
    if (f.methodName) catalogNames.add(f.methodName);
  }
  const signal_temp_labels: Record<string, string> = {};
  for (const id of signal.ids) {
    if (!catalogNames.has(id)) signal_temp_labels[id] = id;
  }
  const project = await createStrategyProject(
    opts.name,
    opts.description || opts.name,
  );
  const base = defaultStrategyConfig();
  return saveStrategyProject({
    ...project,
    config: normalizeStrategyConfig({
      ...project.config,
      engine_mode: mode,
      strategy_code: code,
      universe: parsed.universe || base.universe,
      benchmark: parsed.benchmark || base.benchmark,
      rangeMode: parsed.range_mode === "custom" ? "custom" : "period",
      backtestPeriod: parsed.backtest_period || base.backtestPeriod,
      startDate: parsed.start_date || base.startDate,
      endDate: parsed.end_date || base.endDate,
      commission_rate:
        typeof parsed.commission_rate === "number"
          ? parsed.commission_rate
          : base.commission_rate,
      stamp_tax:
        typeof parsed.stamp_tax === "number" ? parsed.stamp_tax : base.stamp_tax,
      slippage_rate:
        typeof parsed.slippage_rate === "number"
          ? parsed.slippage_rate
          : base.slippage_rate,
      initial_capital:
        typeof parsed.initial_capital === "number"
          ? parsed.initial_capital
          : base.initial_capital,
      top_n: parsed.top_n ?? base.top_n,
      rebalance_days: parsed.rebalance_days ?? base.rebalance_days,
      signal_factor_ids: signal.ids,
      signal_factor_weights: signal.weights,
      signal_factor_powers: signal.powers,
      signal_weight_mode: signal.weightMode,
      signal_temp_labels,
      include_rebalance_logs: true,
    }),
  });
}

/** 社区克隆草稿：未回测前不落库 */
export const STRATEGY_DRAFT_ID = "draft";
const STRATEGY_CLONE_DRAFT_KEY = "svquant_strategy_clone_draft";

export type StrategyCloneDraft = {
  name: string;
  description?: string;
  strategy_code: string;
};

export function stashStrategyCloneDraft(draft: StrategyCloneDraft) {
  sessionStorage.setItem(STRATEGY_CLONE_DRAFT_KEY, JSON.stringify(draft));
}

export function peekStrategyCloneDraft(): StrategyCloneDraft | null {
  try {
    const raw = sessionStorage.getItem(STRATEGY_CLONE_DRAFT_KEY);
    if (!raw) return null;
    const d = JSON.parse(raw) as StrategyCloneDraft;
    if (!d?.strategy_code?.trim() || !d?.name?.trim()) return null;
    return d;
  } catch {
    return null;
  }
}

export function clearStrategyCloneDraft() {
  sessionStorage.removeItem(STRATEGY_CLONE_DRAFT_KEY);
}

/** 打开策略配置草稿页；窄屏同页跳转，桌面优先新标签 */
export function openStrategyDraftInNewTab(draft: StrategyCloneDraft) {
  stashStrategyCloneDraft(draft);
  prepareAuthHandoff();
  const path = `/strategy/research/${STRATEGY_DRAFT_ID}`;
  const narrow =
    typeof window !== "undefined" &&
    window.matchMedia("(max-width: 1023px)").matches;
  if (narrow) {
    window.location.assign(path);
    return;
  }
  const win = window.open(path, "_blank");
  if (!win) {
    window.location.assign(path);
  }
}

export async function saveStrategyProject(
  project: StrategyProject,
): Promise<StrategyProject> {
  const data = await apiJson<{ project: StrategyProject }>(
    `/api/strategy/projects/${encodeURIComponent(project.id)}`,
    {
      method: "PUT",
      body: JSON.stringify({
        id: project.id,
        name: project.name,
        description: project.description,
        config: project.config,
      }),
    },
  );
  clearStrategyClientCache();
  return data.project;
}

export async function deleteStrategyProject(id: string): Promise<void> {
  await apiJson(`/api/strategy/projects/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  clearStrategyClientCache();
}

export async function listStrategyRuns(
  projectId: string,
): Promise<StrategyRunRecord[]> {
  const data = await apiJson<{ runs: StrategyRunRecord[] }>(
    `/api/strategy/projects/${encodeURIComponent(projectId)}/runs`,
  );
  return data.runs || [];
}

/** 当前用户全部策略回测报告（全局检测报告列表） */
export async function listAllStrategyRuns(): Promise<StrategyRunRecord[]> {
  const data = await apiJson<{ runs: StrategyRunRecord[] }>("/api/strategy/runs");
  return data.runs || [];
}

export async function updateStrategyRunRemark(
  runId: string,
  remark: string,
): Promise<StrategyRunRecord> {
  const data = await apiJson<{ run: StrategyRunRecord }>(
    `/api/strategy/runs/${encodeURIComponent(runId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ remark }),
    },
  );
  return data.run;
}

export async function updateStrategyRunFlagged(
  runId: string,
  flagged: boolean,
): Promise<StrategyRunRecord> {
  const data = await apiJson<{ run: StrategyRunRecord }>(
    `/api/strategy/runs/${encodeURIComponent(runId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ flagged }),
    },
  );
  return data.run;
}

export async function getStrategyRun(runId: string): Promise<StrategyRunRecord> {
  const data = await apiJson<{ run: StrategyRunRecord }>(
    `/api/strategy/runs/${encodeURIComponent(runId)}`,
  );
  return data.run;
}

export async function saveStrategyRun(payload: {
  projectId: string;
  name?: string;
  description?: string;
  request: YgStrategyBacktestRequest;
  result: YgBacktestResponse;
  elapsedSec: number;
}): Promise<StrategyRunRecord> {
  const data = await apiJson<{ run: StrategyRunRecord }>("/api/strategy/runs", {
    method: "POST",
    body: JSON.stringify({
      projectId: payload.projectId,
      name: payload.name,
      description: payload.description,
      request: payload.request,
      result: payload.result,
      elapsedSec: payload.elapsedSec,
    }),
  });
  clearStrategyClientCache();
  return data.run;
}

export async function deleteStrategyRun(runId: string): Promise<void> {
  await apiJson(`/api/strategy/runs/${encodeURIComponent(runId)}`, {
    method: "DELETE",
  });
}

/** 打开策略研究：窄屏同页跳转；桌面优先新标签 */
export function openStrategyInNewTab(projectId: string) {
  const path = `/strategy/research/${encodeURIComponent(projectId)}`;
  prepareAuthHandoff();
  const narrow =
    typeof window !== "undefined" &&
    window.matchMedia("(max-width: 1023px)").matches;
  if (narrow) {
    window.location.assign(path);
    return;
  }
  const win = window.open(path, "_blank");
  if (!win) {
    window.location.assign(path);
  }
}

export function requireStrategyUser() {
  if (!getStoredUser()) throw new Error("未登录");
}
