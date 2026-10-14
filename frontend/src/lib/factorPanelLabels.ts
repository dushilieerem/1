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
