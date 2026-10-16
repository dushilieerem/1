import type { YgFactorAnalysis, YgSeriesPoint } from "./ygApi";

/** 与 RE 的 IC 统计一致：使用有效样本、分母 N−1；不足两个样本不可计算。 */
export function sampleStandardDeviation(values: number[]): number | null {
  const finite = values.filter(Number.isFinite);
  if (finite.length < 2) return null;
  const mean = finite.reduce((sum, value) => sum + value, 0) / finite.length;
  return Math.sqrt(finite.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (finite.length - 1));
}

export function icMetrics(series: YgSeriesPoint[], fa: YgFactorAnalysis | null | undefined) {
  const vals = series.map((point) => point.value).filter(Number.isFinite);
  const mean = typeof fa?.ic_mean === "number" && Number.isFinite(fa.ic_mean)
    ? fa.ic_mean
    : vals.length ? vals.reduce((sum, value) => sum + value, 0) / vals.length : 0;
  const std = typeof fa?.ic_std === "number" && Number.isFinite(fa.ic_std)
    ? fa.ic_std
    : sampleStandardDeviation(vals);
  const ir = std == null ? null : std > 1e-12 ? mean / std : 0;
  const posPct = vals.length ? 100 * vals.filter((value) => value > 0).length / vals.length : 0;
  return { mean, std, ir, posPct };
}
