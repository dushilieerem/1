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

export type YgFactorAnalysis = {
  ic_mean?: number | null;
  ic_std?: number | null;
  rank_ic_mean?: number | null;
  layered_returns?: Record<string, number | null>;
  cumulative_series?: YgLayerPoint[] | null;
  /** 诊断图口径定义（可选） */
  definition?: Record<string, unknown> | null;
  ic_series?: YgSeriesPoint[] | null;
  cumulative_ic_series?: YgSeriesPoint[] | null;
  rolling_ir_series?: YgSeriesPoint[] | null;
  industry_equity_curves?: YgIndustryEquityCurve[] | null;
  industry_group_equity_curves?: YgIndustryGroupEquityCurve[] | null;
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
  error?: string | null;
};

/** 对齐 FACTOR-BACKTEST-API.md；勿传已移除字段（会 422） */
export type YgBacktestRequest = {
  factor_code: string;
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
};

export async function ygBacktestFactor(body: YgBacktestRequest, signal?: AbortSignal) {
  const res = await fetch("/yg-api/api/backtest/factor", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
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
