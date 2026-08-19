import { authHeaders } from "./auth";

export type YgDrawdown = {
  start: string;
  end: string;
  depth?: number | null;
  days?: number | null;
  peak?: number | null;
  trough?: number | null;
  recovery?: string | null;
};

export type YgCurvePoint = {
  date: string;
  value: number;
  drawdown?: number | null;
};

export type YgLayerPoint = {
  date: string;
  layer1?: number | null;
  layer2?: number | null;
  layer3?: number | null;
  layer4?: number | null;
  layer5?: number | null;
  layer6?: number | null;
  layer7?: number | null;
  layer8?: number | null;
  layer9?: number | null;
  layer10?: number | null;
  [key: string]: string | number | null | undefined;
};

/** 因子诊断：日频 IC / 累计 IC / 滚动 IR 点 */
export type YgSeriesPoint = {
  date: string;
  value: number;
  sample_size?: number | null;
  window?: number | null;
};

export type YgIndustryEquityCurve = {
  industry_code?: string;
  industry_name?: string;
  points?: Array<{ date: string; value: number }>;
};

export type YgIndustryGroupEquityCurve = {
  industry_code?: string;
  industry_name?: string;
  points?: Array<{
    date: string;
    groups?: Record<string, number | null>;
  }>;
};

export type YgQuantileMetric = {
  quantile: string;
  annual_return?: number | null;
  volatility?: number | null;
  sharpe?: number | null;
  max_drawdown?: number | null;
  annual_excess_return?: number | null;
  excess_volatility?: number | null;
  information_ratio?: number | null;
  benchmark_win_rate?: number | null;
};

export type YgFactorAnalysis = {
  ic_mean?: number | null;
  ic_std?: number | null;
  rank_ic_mean?: number | null;
  layered_returns?: Record<string, number | null>;
  cumulative_series?: YgLayerPoint[] | null;
  /** 各分位相对基准绩效（分组绩效分析表） */
  quantile_metrics?: YgQuantileMetric[] | null;
  /** 诊断图口径定义（可选） */
  definition?: Record<string, unknown> | null;
  ic_series?: YgSeriesPoint[] | null;
  cumulative_ic_series?: YgSeriesPoint[] | null;
  rolling_ir_series?: YgSeriesPoint[] | null;
  industry_equity_curves?: YgIndustryEquityCurve[] | null;
  industry_group_equity_curves?: YgIndustryGroupEquityCurve[] | null;
};

/** 策略回测：单笔目标权重变化（非成交回报） */
export type YgRebalanceTrade = {
  symbol: string;
  /** 证券简称；新版 RE 返回 */
  name?: string | null;
  side: string;
  previous_weight: number;
  target_weight: number;
  weight_change: number;
};

export type YgRebalanceLog = {
  date: string;
  trades: YgRebalanceTrade[];
};

export type YgHolding = {
  symbol: string;
  name?: string | null;
  weight: number;
};

/** 事件回测：订单 */
export type YgEventOrder = {
  order_id?: string;
  symbol?: string;
  quantity?: number | null;
  target_value?: number | null;
  side?: string;
  status?: string;
  reason_code?: string | null;
  submitted_at?: string;
};

/** 事件回测：成交 */
export type YgEventFill = {
  order_id?: string;
  symbol?: string;
  side?: string;
  quantity?: number | null;
  price?: number | null;
  timestamp?: string;
  commission?: number | null;
  stamp_tax?: number | null;
};

/** 事件回测：日终账户快照 */
export type YgEventPositionSnap = {
  timestamp?: string;
  cash?: number | null;
  total_value?: number | null;
  positions?: Record<string, number> | null;
  sellable_quantities?: Record<string, number> | null;
};

export type YgBacktestResponse = {
  metrics?: Record<string, number | null>;
  equity_curve?: YgCurvePoint[] | null;
  drawdowns?: YgDrawdown[];
  annual_returns?: Array<{ year: number; return_value: number }>;
  factor_analysis?: YgFactorAnalysis | null;
  benchmark_curve?: YgCurvePoint[] | null;
  excess_return?: number | null;
  date_range?: { start?: string; end?: string } | null;
  final_equity?: number | null;
  meta?: Record<string, unknown> | null;
  positions?: Array<{
    date: string;
    holdings: YgHolding[];
  }> | null;
  /** include_rebalance_logs=true 时返回（向量化） */
  rebalance_logs?: YgRebalanceLog[] | null;
  /** 事件模式明细（与 include_rebalance_logs 无关） */
  orders?: YgEventOrder[] | null;
  fills?: YgEventFill[] | null;
  event_positions?: YgEventPositionSnap[] | null;
  events?: Array<Record<string, unknown>> | null;
  assumptions?: Record<string, unknown> | null;
  error?: string | null;
};

/** 对齐 06-research-api.md §4.2；勿传已移除字段（会 422） */
export type YgBacktestRequest = {
  /** 自定义/本地抽码；纯 RE 内置单因子可不传 */
  factor_code?: string;
  /** RE 内置库名；单库字符串，跨库数组 */
  library_name?: string | string[];
  factor_name?: string;
  portfolio_type?: string;
  universe?: string;
  start?: string | null;
  end?: string | null;
  filter_limit_up?: boolean;
  filter_suspended?: boolean;
  rebalance_days?: number;
  groups?: number;
  benchmark?: string;
  commission_rate?: number;
  stamp_tax?: number;
  slippage_rate?: number;
  /** core=核心回测（默认） | full=额外 IC/FF3/行业 */
  analysis_level?: "core" | "full";
  /** 仅 SVQuant 落库：当次左侧配置快照，不发给 RE */
  _svquant_ui?: Record<string, unknown>;
  /** 仅落库：草稿因子 */
  _svquantDraftFactor?: Record<string, unknown>;
};

/** 去掉空 factor_code，避免纯 library_name 请求被脏字段干扰 */
export function serializeYgFactorBody(body: YgBacktestRequest): Record<string, unknown> {
  const out: Record<string, unknown> = { ...body };
  if (out.factor_code == null || String(out.factor_code).trim() === "") {
    delete out.factor_code;
  }
  if (out.library_name == null) {
    delete out.library_name;
  }
  delete out._svquantDraftFactor;
  delete out._svquant_ui;
  return out;
}

/**
 * 因子回测：经 Vite `/yg-api` 直打 ResearchEngine（同步等结果）。
 * 算数不再经本机 :8766 队列；保存项目 / 存检测 run 仍走本机 API。
 */
export async function ygBacktestFactor(
  body: YgBacktestRequest,
  signal?: AbortSignal,
  opts?: {
    /** 已发出 RE 请求时回调（无本机 job 排队） */
    onQueued?: (info: {
      jobId: string;
      maxInflight: number;
      queued: number;
      running: number;
    }) => void;
    onStarted?: () => void;
  },
) {
  opts?.onStarted?.();
  // 兼容旧日志回调：直打 RE 无 job 队列
  opts?.onQueued?.({
    jobId: "",
    maxInflight: 0,
    queued: 0,
    running: 1,
  });

  const headers = { "Content-Type": "application/json", ...authHeaders() };
  const res = await fetch("/yg-api/api/backtest/factor", {
    method: "POST",
    headers,
    body: JSON.stringify(serializeYgFactorBody(body)),
    signal,
  });
  const text = await res.text();
  let data: YgBacktestResponse & { detail?: unknown; error?: string };
  try {
    data = JSON.parse(text) as typeof data;
  } catch {
    throw new Error(
      res.ok ? "响应不是 JSON" : `HTTP ${res.status}: ${text.slice(0, 200)}`,
    );
  }
  if (!res.ok) {
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : data.error || text.slice(0, 200);
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return data as YgBacktestResponse;
}

/** 策略回测：对齐 06-research-api.md + Strategy/libraries/backtest-strategy.md */
export type YgStrategyEngineMode = "vectorized" | "event";

export type YgStrategyBacktestRequest = {
  /** 与 strategy_id 二选一 */
  strategy_code?: string;
  /** 平台库策略 ID（RE 侧 index.yaml） */
  strategy_id?: string;
  strategy_version?: string;
  /** vectorized（默认）| event；须与策略契约一致 */
  engine_mode?: YgStrategyEngineMode;
  universe?: string;
  start?: string | null;
  end?: string | null;
  benchmark?: string;
  commission_rate?: number;
  stamp_tax?: number;
  slippage_rate?: number;
  initial_capital?: number;
  include_positions?: boolean;
  /** 是否返回目标权重变化的调仓日志（默认 false；研究页可勾选） */
  include_rebalance_logs?: boolean;
  /**
   * 仅 SVQuant 落库用：左侧因子选择快照。
   * serializeYgStrategyBody 会剥离，不会发给 ResearchEngine。
   */
  _svquant_ui?: {
    signal_factor_ids?: string[];
    signal_factor_weights?: number[];
    signal_factor_powers?: number[];
    signal_weight_mode?: "sum" | "product" | "custom";
    signal_temp_labels?: Record<string, string>;
  };
};

export function serializeYgStrategyBody(
  body: YgStrategyBacktestRequest,
): Record<string, unknown> {
  const out: Record<string, unknown> = { ...body };
  delete out._svquant_ui;
  const code = out.strategy_code != null ? String(out.strategy_code).trim() : "";
  const sid = out.strategy_id != null ? String(out.strategy_id).trim() : "";
  if (!code) delete out.strategy_code;
  else out.strategy_code = code;
  if (!sid) delete out.strategy_id;
  else out.strategy_id = sid;
  if (out.strategy_version == null || String(out.strategy_version).trim() === "") {
    delete out.strategy_version;
  }
  const mode = out.engine_mode != null ? String(out.engine_mode).trim() : "";
  if (mode === "event" || mode === "vectorized") out.engine_mode = mode;
  else delete out.engine_mode;
  return out;
}

export async function ygBacktestStrategy(
  body: YgStrategyBacktestRequest,
  signal?: AbortSignal,
) {
  const payload = serializeYgStrategyBody(body);
  if (!payload.strategy_code && !payload.strategy_id) {
    throw new Error("strategy_code 与 strategy_id 至少提供其一");
  }
  const res = await fetch("/yg-api/api/backtest/strategy", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  const text = await res.text();
  let data: YgBacktestResponse;
  try {
    data = JSON.parse(text) as YgBacktestResponse;
  } catch {
    throw new Error(res.ok ? "响应不是 JSON" : `HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  return data;
}

export async function ygHealth() {
  const res = await fetch("/yg-api/api/health");
  if (!res.ok) throw new Error(`YGQuant 不通 HTTP ${res.status}`);
  return res.json() as Promise<{ status?: string; version?: string }>;
}
