/**
 * 因子面板的展示文案映射。
 *
 * 放在 lib 层是为了可被测试直接引用——页面模块会连带引入 CodeMirror、
 * react-router 等重依赖，不适合在 jsdom 下单测。
 */

/** RE 的 `factor_analysis.definition.ic_unavailable_reason` → 中文说明。 */
export const IC_UNAVAILABLE_LABELS: Record<string, string> = {
  missing_inputs: "因子值或远期收益缺失",
  no_common_axis: "因子值与远期收益没有共同日期或标的",
  insufficient_cross_section: "没有任何交易日满足 ≥2 个有效样本（因子基本无值）",
  zero_cross_sectional_variance: "横截面无方差（因子在该区间近似常数）",
};

/** 分位方向：RE `portfolio/grouping.py` 的 `rank_groups` 把 Q1 定为因子值最高组。 */
export const RE_Q1_DIRECTION_HINT = "RE 口径：Q1 = 因子值最大组、QN = 因子值最小组";

/**
 * 组合类型 → 报告页展示的口径说明。
 *
 * RE 的主组合由请求的 `portfolio_type` 决定（`portfolio/engine.py` 的
 * `_group_target`）：纯多 = 组号 1（最高分位）等权；多空 = 组号 1 减组号 N。
 * 累计收益、最大回撤、胜率、Sharpe 都是这条主组合的口径，不是某个分组。
 */
export const PORTFOLIO_CONVENTION: Record<string, string> = {
  long_only: "纯多 = 做多 Q1（因子值最大组）等权组合",
  long_short: "多空 = Q1 − QN（做多最高组、做空最低组）",
};

export function portfolioConvention(code: string | null | undefined, groups?: number | null): string {
  if (code === "long_short") {
    return `多空 = Q1 − Q${clampGroups(groups ?? 5)}（做多最高组、做空最低组）`;
  }
  return PORTFOLIO_CONVENTION[String(code || "")] || "";
}

/** RE 的 `layered_returns.groups` / 请求的 groups：界面只接受 2–10 组。 */
export const MIN_GROUPS = 2;
export const MAX_GROUPS = 10;

export function clampGroups(groups: number | null | undefined): number {
  const n = Math.floor(Number(groups));
  if (!Number.isFinite(n)) return 5;
  return Math.min(Math.max(n, MIN_GROUPS), MAX_GROUPS);
}

/**
 * 分位曲线的层键：`layer1..layerN` 对应 RE `cumulative_series` 的列序，
 * 也就是 Q1..QN。**不做 5 组截断**——分组可选 3/5/10，画 5 条会把 10 组的
 * 图悄悄变成"十分位的上半段"。
 */
export function groupLayerKeys(groups: number | null | undefined): string[] {
  return Array.from({ length: clampGroups(groups) }, (_, i) => `layer${i + 1}`);
}

/** 层键 → 分位标签：`layer3` → `Q3`；认不出时按序号回退。 */
export function quantileLabel(layerKey: string, index: number): string {
  const m = /^layer(\d+)$/i.exec(layerKey || "");
  return `Q${m ? Number(m[1]) : index + 1}`;
}

/**
 * IC 单元格的悬停说明。
 *
 * 返回 `null` 表示「没有原因可解释」——包括还没算、算失败、以及老响应没有该
 * 字段，此时保持原先的「—」即可，**不要编造原因**。RE 新增了未知取值时按原样
 * 透出，不吞掉。
 */
export function icUnavailableHint(reason: string | null | undefined): string | null {
  if (!reason) return null;
  return `IC 不可用（非计算失败）：${IC_UNAVAILABLE_LABELS[reason] || reason}`;
}
