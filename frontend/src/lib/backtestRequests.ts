/**
 * 回测请求体组装。
 *
 * 从两个检测页抽出，放在 lib 层是为了可被测试直接引用——页面模块会连带引入
 * CodeMirror、react-router 等重依赖，不适合在 jsdom 下单测。
 * 「四个过滤开关确实进了请求体」这件事没有类型层面的强制（字段都是可选的），
 * 只靠通读页面代码很容易漏，因此需要这里的纯函数来兜住。
 */

import type { DetectProjectConfig } from "./detectStore";
import type { StrategyProjectConfig } from "./strategyStore";
import type { YgBacktestRequest, YgStrategyBacktestRequest } from "./ygApi";

/** 因子检测请求：由左侧配置 + 因子代码/库名部分拼装。 */
export function buildFactorDetectRequest(
  cfg: DetectProjectConfig,
  parts: Partial<YgBacktestRequest>,
  range: { start: string; end: string },
): YgBacktestRequest {
  return {
    ...parts,
    portfolio_type: cfg.portfolioType,
    universe: cfg.universe,
    start: range.start,
    end: range.end,
    // 顺序与后端文档一致：停牌 / ST / 涨停 / 跌停
    filter_suspended: cfg.filterSuspended,
    filter_st: cfg.filterSt,
    filter_limit_up: cfg.filterLimitUp,
    filter_limit_down: cfg.filterLimitDown,
    benchmark: cfg.benchmark,
    groups: Math.min(5, Math.max(1, cfg.groups || 5)),
    rebalance_days: cfg.rebalanceDays,
    commission_rate: cfg.commissionRate,
    stamp_tax: cfg.stampTax,
    slippage_rate: cfg.slippageRate,
    analysis_level: cfg.analysisLevel || "core",
  };
}

/** 策略检测请求：strategy_id 与 strategy_code 二选一。 */
export function buildStrategyBacktestRequest(
  cfg: StrategyProjectConfig,
  opts: {
    strategyId: string;
    snapshotCode: string;
    range: { start: string | null; end: string | null };
  },
): YgStrategyBacktestRequest {
  return {
    ...(opts.strategyId
      ? { strategy_id: opts.strategyId }
      : { strategy_code: opts.snapshotCode }),
    engine_mode: cfg.engine_mode,
    universe: cfg.universe,
    start: opts.range.start,
    end: opts.range.end,
    benchmark: cfg.benchmark,
    commission_rate: cfg.commission_rate,
    stamp_tax: cfg.stamp_tax,
    slippage_rate: cfg.slippage_rate,
    initial_capital: cfg.initial_capital,
    include_positions: false,
    include_rebalance_logs: cfg.include_rebalance_logs,
    // 顺序与后端文档一致：停牌 / ST / 涨停 / 跌停
    filter_suspended: cfg.filter_suspended,
    filter_st: cfg.filter_st,
    filter_limit_up: cfg.filter_limit_up,
    filter_limit_down: cfg.filter_limit_down,
  };
}
