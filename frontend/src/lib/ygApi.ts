import { researchFetch as fetch } from "./researchClient";
import { authHeaders } from "./researchClient";

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
  /** 该分组的日均单边换手（Σ|Δw|/2，逐日均值、不年化）；RE 新版本才有。 */
  turnover?: number | null;
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

/** 对齐 ResearchEngine 因子回测 API 契约；勿传已移除字段（会 422） */
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
  /** 是否过滤 ST、*ST */
  filter_st?: boolean;
  /** 是否过滤跌停 */
  filter_limit_down?: boolean;
  rebalance_days?: number;
  groups?: number;
  benchmark?: string;
  commission_rate?: number;
  stamp_tax?: number;
  slippage_rate?: number;
  /** core=核心回测（默认） | full=额外 IC/FF3/行业 */
  analysis_level?: "core" | "full";
  /** 成交时点：当日收盘 / 次日收盘（默认） / 次日开盘 */
  execution_timing?: "same_close" | "next_close" | "next_open";
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
 * 计算类请求走本机薄 BFF（方案 A）：浏览器只打同源 /api，由 :8766 转发对方。
 * 不直连对方地址，便于以后公网只暴露本站。
 */
function localApiUrl(path: string): string {
  return path.startsWith("/") ? path : `/${path}`;
}

type YgAsyncRunTask = {
  run_id?: string;
  status?: string;
  poll_url?: string;
  error?: string | null;
  result?: YgBacktestResponse | null;
  cancel_requested?: boolean;
  detail?: unknown;
};

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const t = window.setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      window.clearTimeout(t);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

function parseJsonText(text: string): Record<string, unknown> {
  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function errFromBody(data: Record<string, unknown>, status: number, text: string): string {
  if (typeof data.detail === "string" && data.detail.trim()) return data.detail;
  if (typeof data.error === "string" && data.error.trim()) return data.error;
  const slice = text.slice(0, 200).trim();
  return slice || `HTTP ${status}`;
}

/** 是否已是完整回测报表（旧同步 POST 或任务 result） */
function looksLikeBacktestResult(
  data: Record<string, unknown> | null | undefined,
): data is YgBacktestResponse {
  if (!data || typeof data !== "object") return false;
  return (
    "metrics" in data ||
    "equity_curve" in data ||
    "factor_analysis" in data ||
    "date_range" in data
  );
}

async function cancelBacktestRun(
  kind: "factor" | "strategy",
  runId: string,
): Promise<void> {
  const id = String(runId || "").trim();
  if (!id) return;
  try {
    await fetch(
      localApiUrl(`/api/backtest/${kind}/${encodeURIComponent(id)}`),
      {
        method: "DELETE",
        headers: { ...authHeaders() },
        cache: "no-store",
      },
    );
  } catch {
    /* 取消尽力而为 */
  }
}

async function submitAndPollBacktest(
  kind: "factor" | "strategy",
  payload: string,
  signal?: AbortSignal,
  opts?: {
    onQueued?: (info: {
      jobId: string;
      maxInflight: number;
      queued: number;
      running: number;
    }) => void;
    onStarted?: () => void;
  },
): Promise<YgBacktestResponse> {
  const headers = { "Content-Type": "application/json", ...authHeaders() };
  const submitPath = `/api/backtest/${kind}`;

  let submitRes: Response | null = null;
  let submitText = "";
  let submitData: Record<string, unknown> = {};

  for (let attempt = 0; attempt < 4; attempt++) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    submitRes = await fetch(localApiUrl(submitPath), {
      method: "POST",
      headers,
      body: payload,
      signal,
      cache: "no-store",
    });
    submitText = await submitRes.text();
    submitData = parseJsonText(submitText);

    if (submitRes.status !== 429) break;
    const retryAfter = Number(submitRes.headers.get("Retry-After") || "1");
    await sleep(Math.max(1, retryAfter) * 1000, signal);
  }

  if (!submitRes) throw new Error("提交失败");

  if (submitRes.ok && submitRes.status !== 202 && looksLikeBacktestResult(submitData)) {
    opts?.onStarted?.();
    opts?.onQueued?.({ jobId: "", maxInflight: 0, queued: 0, running: 1 });
    return submitData as YgBacktestResponse;
  }

  const runId = String(submitData.run_id || "").trim();
  if (!(submitRes.status === 202 || (submitRes.ok && runId))) {
    throw new Error(errFromBody(submitData, submitRes.status, submitText));
  }
  if (!runId) throw new Error("提交成功但未返回任务编号");

  opts?.onQueued?.({
    jobId: runId,
    maxInflight: 0,
    queued: 1,
    running: 0,
  });

  const pollPath =
    typeof submitData.poll_url === "string" && submitData.poll_url.startsWith("/api/")
      ? submitData.poll_url
      : `/api/backtest/${kind}/${encodeURIComponent(runId)}`;

  let delayMs = 1000;
  let sawRunning = false;

  try {
    while (true) {
      if (signal?.aborted) {
        await cancelBacktestRun(kind, runId);
        throw new DOMException("Aborted", "AbortError");
      }
      await sleep(delayMs, signal);

      const pollRes = await fetch(localApiUrl(pollPath), {
        method: "GET",
        headers: { ...authHeaders() },
        signal,
        cache: "no-store",
      });
      const pollText = await pollRes.text();
      const task = parseJsonText(pollText) as YgAsyncRunTask & Record<string, unknown>;

      if (pollRes.status === 404) {
        throw new Error("任务已过期或不存在，请重试");
      }
      if (pollRes.status === 429) {
        const retryAfter = Number(pollRes.headers.get("Retry-After") || "1");
        delayMs = Math.max(1000, retryAfter * 1000);
        continue;
      }
      if (!pollRes.ok) {
        throw new Error(errFromBody(task, pollRes.status, pollText));
      }

      const status = String(task.status || "");
      if (status === "running" && !sawRunning) {
        sawRunning = true;
        opts?.onStarted?.();
      } else if (status === "succeeded") {
        const result = task.result;
        if (!looksLikeBacktestResult(result as Record<string, unknown>)) {
          throw new Error("已完成但未返回结果，请重试");
        }
        return result as YgBacktestResponse;
      } else if (status === "failed") {
        throw new Error(String(task.error || "失败").trim() || "失败");
      } else if (status === "cancelled") {
        throw new DOMException("Aborted", "AbortError");
      }

      delayMs = delayMs < 2000 ? 2000 : 3000;
    }
  } catch (e) {
    if ((e as Error)?.name === "AbortError") {
      await cancelBacktestRun(kind, runId);
    }
    throw e;
  }
}

/**
 * 因子回测：本机 BFF 提交 → 轮询 GET（对方异步；本机不建队列）。
 */
export async function ygBacktestFactor(
  body: YgBacktestRequest,
  signal?: AbortSignal,
  opts?: {
    onQueued?: (info: {
      jobId: string;
      maxInflight: number;
      queued: number;
      running: number;
    }) => void;
    onStarted?: () => void;
  },
) {
  return submitAndPollBacktest(
    "factor",
    JSON.stringify(serializeYgFactorBody(body)),
    signal,
    opts,
  );
}

/** 策略回测：对齐 ResearchEngine 策略回测 API 契约 */
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
  /** 是否过滤停牌（事件模式下由撮合层强制拦截，该参数不额外生效） */
  filter_suspended?: boolean;
  /** 是否过滤 ST、*ST（事件模式下只拒绝买入） */
  filter_st?: boolean;
  /** 是否过滤涨停（事件模式下由撮合层强制拦截，该参数不额外生效） */
  filter_limit_up?: boolean;
  /** 是否过滤跌停（事件模式下由撮合层强制拦截，该参数不额外生效） */
  filter_limit_down?: boolean;
  /** 成交时点：当日收盘 / 次日收盘（默认） / 次日开盘 */
  execution_timing?: "same_close" | "next_close" | "next_open";
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
  return submitAndPollBacktest(
    "strategy",
    JSON.stringify(payload),
    signal,
  );
}

export async function ygHealth() {
  const res = await fetch(localApiUrl("/api/re/health"));
  if (!res.ok) throw new Error(`计算服务不通 HTTP ${res.status}`);
  return res.json() as Promise<{ status?: string; version?: string }>;
}
