/** 平台策略库（Strategy/libraries）— 仅内置；研究项目在「策略研究」 */

import { authHeaders, assertAuthConsistency } from "./auth";
import {
  inferEngineModeFromCode,
  parseParamsFromCode,
  wrapBuiltinLibraryStrategy,
} from "./strategyCodeSync";
import { parseLibrarySignalSelection } from "./strategyFactorSync";
import {
  createStrategyProject,
  defaultStrategyConfig,
  listStrategyProjects,
  openStrategyInNewTab,
  saveStrategyProject,
  type StrategyEngineMode,
  type StrategyProject,
  type StrategyProjectConfig,
} from "./strategyStore";
import type { UserLibraryStrategy } from "./userStrategyLibraries";
import type { YgStrategyBacktestRequest } from "./ygApi";

/** 入库可选分类：内置常见类 + 其他 */
export const STRATEGY_ARCHIVE_CATEGORIES = [
  "趋势",
  "动量",
  "反转",
  "低波动",
  "小市值",
  "最小方差",
  "统计套利",
  "其他",
] as const;

export type StrategyArchiveCategory =
  (typeof STRATEGY_ARCHIVE_CATEGORIES)[number];

/** strategy_type（英文键）→ 页面中文分类 */
export const STRATEGY_TYPE_LABELS: Record<string, string> = {
  trend: "趋势",
  momentum: "动量",
  reversal: "反转",
  low_volatility: "低波动",
  minimum_variance: "最小方差",
  statistical_arbitrage: "统计套利",
  small_cap: "小市值",
  custom: "自定义",
};

export function strategyTypeLabel(typeOrLabel: string | undefined | null): string {
  const raw = (typeOrLabel || "").trim();
  if (!raw) return "其他";
  if (STRATEGY_TYPE_LABELS[raw]) return STRATEGY_TYPE_LABELS[raw];
  // 已是中文或未知类型，原样返回
  return raw;
}

export type BuiltinStrategyMeta = {
  id: string;
  name: string;
  strategy_type: string;
  strategy_type_label: string;
  execution_mode: string;
  current_version: string;
  tags: string[];
  file: string;
  entrypoint: string;
  source: "builtin";
};

async function apiJson<T>(url: string): Promise<T> {
  assertAuthConsistency();
  const res = await fetch(url, { headers: { ...authHeaders() } });
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

export async function listBuiltinStrategies(): Promise<BuiltinStrategyMeta[]> {
  const data = await apiJson<{ items: BuiltinStrategyMeta[] }>(
    "/api/strategy/library",
  );
  return (data.items || []).map((item) => ({
    ...item,
    strategy_type_label: strategyTypeLabel(
      item.strategy_type_label || item.strategy_type,
    ),
  }));
}

export async function getBuiltinStrategySource(
  id: string,
  version?: string,
): Promise<{
  id: string;
  name: string;
  version: string;
  strategy_code: string;
  strategy_type_label: string;
  execution_mode: string;
  tags: string[];
}> {
  const q = version ? `?version=${encodeURIComponent(version)}` : "";
  return apiJson(`/api/strategy/library/${encodeURIComponent(id)}${q}`);
}

function normalizeEngineMode(
  mode?: string | null,
  code?: string,
): StrategyEngineMode {
  if (mode === "event" || mode === "vectorized") return mode;
  return inferEngineModeFromCode(code || "");
}

/** 库源码 → 研究页配置；事件策略不包成 FactorPortfolio */
export function configFromLibraryCode(
  rawCode: string,
  opts?: { engineMode?: StrategyEngineMode | string | null },
): Partial<StrategyProjectConfig> {
  const mode = normalizeEngineMode(opts?.engineMode, rawCode);
  const code = wrapBuiltinLibraryStrategy(rawCode);
  const parsed = parseParamsFromCode(code);
  const base = defaultStrategyConfig();
  if (mode === "event") {
    return {
      ...base,
      engine_mode: "event",
      strategy_code: code,
      universe: parsed.universe || base.universe,
      benchmark: parsed.benchmark || base.benchmark,
      rangeMode: parsed.range_mode === "custom" ? "custom" : "period",
      backtestPeriod: parsed.backtest_period || "3y",
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
      signal_factor_ids: [],
      signal_factor_weights: [],
      signal_factor_powers: [],
      signal_temp_labels: {},
      include_rebalance_logs: true,
    };
  }
  const signal = parseLibrarySignalSelection(code);
  return {
    ...base,
    engine_mode: "vectorized",
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
    include_rebalance_logs: true,
  };
}

/** 某次回测 request → 检测页配置（历史快照） */
export function configFromRunRequest(
  req: YgStrategyBacktestRequest | Record<string, unknown> | null | undefined,
): StrategyProjectConfig {
  const r = (req || {}) as YgStrategyBacktestRequest;
  const code = String(r.strategy_code || "").trim();
  const mode = normalizeEngineMode(r.engine_mode, code);
  const fromCode = code
    ? configFromLibraryCode(code, { engineMode: mode })
    : defaultStrategyConfig();
  const hasRange = Boolean(r.start && r.end);
  return {
    ...defaultStrategyConfig(),
    ...fromCode,
    engine_mode: mode,
    strategy_code: code || String(fromCode.strategy_code || ""),
    universe: String(r.universe || fromCode.universe || "CSI500"),
    benchmark: String(r.benchmark || fromCode.benchmark || "CSI300"),
    rangeMode: hasRange ? "custom" : fromCode.rangeMode || "period",
    startDate: hasRange
      ? String(r.start)
      : String(fromCode.startDate || ""),
    endDate: hasRange ? String(r.end) : String(fromCode.endDate || ""),
    commission_rate:
      typeof r.commission_rate === "number"
        ? r.commission_rate
        : Number(fromCode.commission_rate) || 0.0003,
    stamp_tax:
      typeof r.stamp_tax === "number"
        ? r.stamp_tax
        : Number(fromCode.stamp_tax) || 0.001,
    slippage_rate:
      typeof r.slippage_rate === "number"
        ? r.slippage_rate
        : Number(fromCode.slippage_rate) || 0.001,
    initial_capital:
      typeof r.initial_capital === "number"
        ? r.initial_capital
        : Number(fromCode.initial_capital) || 1_000_000,
    include_rebalance_logs:
      typeof r.include_rebalance_logs === "boolean"
        ? r.include_rebalance_logs
        : true,
  };
}

/** 复用同 library_ref 研究项目并刷新为库快照；否则新建 */
async function openOrCreateResearchProject(opts: {
  name: string;
  description?: string;
  strategyCode: string;
  /** 如 library:xxx / userlib:123 */
  libraryRef?: string;
  engineMode?: StrategyEngineMode | string | null;
}): Promise<StrategyProject> {
  const title = opts.name.trim();
  if (!title) throw new Error("检测名称不能为空");
  const fromLib = configFromLibraryCode(opts.strategyCode, {
    engineMode: opts.engineMode,
  });
  const list = await listStrategyProjects();
  const libKey = opts.libraryRef || null;
  const existing = list.find((p) => {
    if (libKey && (p.config as { library_ref?: string }).library_ref === libKey) {
      return true;
    }
    return false;
  });
  if (existing) {
    const saved = await saveStrategyProject({
      ...existing,
      description: opts.description || existing.description || title,
      config: {
        ...existing.config,
        ...fromLib,
        library_ref: libKey || existing.config.library_ref,
      },
    });
    openStrategyInNewTab(saved.id);
    return saved;
  }
  const created = await createStrategyProject(title, opts.description || title);
  const saved = await saveStrategyProject({
    ...created,
    description: opts.description || title,
    config: {
      ...created.config,
      ...fromLib,
      library_ref: libKey || undefined,
    },
  });
  openStrategyInNewTab(saved.id);
  return saved;
}

/** 内置策略库「检测」 */
export async function openBuiltinStrategyDetect(meta: BuiltinStrategyMeta) {
  const src = await getBuiltinStrategySource(meta.id, meta.current_version);
  const mode = normalizeEngineMode(
    src.execution_mode || meta.execution_mode,
    src.strategy_code,
  );
  return openOrCreateResearchProject({
    name: meta.name,
    description: meta.name,
    strategyCode: src.strategy_code,
    libraryRef: `library:${meta.id}`,
    engineMode: mode,
  });
}

/** 用户策略库入库项「检测」：按入库快照开/刷新研究项目 */
export async function openUserLibraryStrategyDetect(item: UserLibraryStrategy) {
  const code = (item.body || "").trim();
  if (!code) throw new Error("该策略没有代码快照");
  return openOrCreateResearchProject({
    name: item.name,
    description: item.description || item.name,
    strategyCode: code,
    libraryRef: `userlib:${item.id}`,
    engineMode: inferEngineModeFromCode(code),
  });
}

/** 策略库「新增」：命名后立刻建研究项目并打开 */
export async function createNamedStrategyAndOpen(name: string) {
  const title = name.trim();
  if (!title) throw new Error("请填写检测名称");
  const created = await createStrategyProject(title, title);
  openStrategyInNewTab(created.id);
  return created;
}
