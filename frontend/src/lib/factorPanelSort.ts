/** 无有效数值的指标始终放最后，避免升序时被误认为最小值。 */
export function comparePanelMetric(a: unknown, b: unknown, direction: "asc" | "desc"): number {
  const av = typeof a === "number" && Number.isFinite(a) ? a : null;
  const bv = typeof b === "number" && Number.isFinite(b) ? b : null;
  if (av === null) return bv === null ? 0 : 1;
  if (bv === null) return -1;
  return (direction === "asc" ? 1 : -1) * (av - bv);
}
