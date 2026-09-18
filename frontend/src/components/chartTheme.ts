/** NBQuant 因子图主题：偏亮的青 / 珊瑚 / 天蓝（避免过暗墨色） */

export const CHART = {
  ink: "#0d9488",
  inkSoft: "#2dd4bf",
  amber: "#f97316",
  amberSoft: "#fb923c",
  stone: "#38bdf8",
  stoneSoft: "#7dd3fc",
  sage: "#34d399",
  sand: "#fbbf24",
  muted: "#64748b",
  grid: "#e2e8f0",
  axis: "#64748b",
  zero: "#94a3b8",
  cardBorder: "#e2e8f0",
  positive: "#14b8a6",
  negative: "#fb7185",
  bench: "#6366f1",
} as const;

/** 分层 Q1→Qn：亮色阶 */
export const QUANTILE_PALETTE = [
  "#22d3ee",
  "#38bdf8",
  "#a78bfa",
  "#fb923c",
  "#f43f5e",
  "#94a3b8",
] as const;

/** 多序列线色 */
export const SERIES_PALETTE = [
  "#14b8a6",
  "#f97316",
  "#38bdf8",
  "#a78bfa",
  "#f43f5e",
  "#84cc16",
  "#eab308",
  "#ec4899",
  "#06b6d4",
  "#8b5cf6",
  "#f59e0b",
  "#10b981",
  "#6366f1",
  "#ef4444",
  "#0ea5e9",
  "#d946ef",
  "#65a30d",
  "#f472b6",
  "#2dd4bf",
  "#fb7185",
  "#60a5fa",
  "#c084fc",
  "#4ade80",
  "#fbbf24",
  "#f87171",
  "#67e8f9",
  "#a3e635",
  "#e879f9",
  "#38bdf8",
  "#fdba74",
  "#86efac",
] as const;

/** 风格因子：SMB/HML/RMW/CMA */
export const STYLE_PALETTE = {
  MKT: "#6366f1",
  SMB: "#f43f5e",
  HML: "#14b8a6",
  RMW: "#f97316",
  CMA: "#38bdf8",
} as const;

export function darkTooltip() {
  return {
    trigger: "axis" as const,
    backgroundColor: "rgba(15, 23, 42, 0.88)",
    borderWidth: 0,
    textStyle: { color: "#f8fafc", fontSize: 12 },
    extraCssText: "border-radius:10px;box-shadow:0 8px 24px rgba(15,23,42,0.18);",
  };
}

export function axisCategory(extra: Record<string, unknown> = {}) {
  return {
    type: "category" as const,
    boundaryGap: false,
    axisLine: { lineStyle: { color: CHART.grid } },
    axisLabel: { color: CHART.axis, fontSize: 11 },
    axisTick: { show: false },
    ...extra,
  };
}

export function axisValuePct(extra: Record<string, unknown> = {}) {
  return {
    type: "value" as const,
    axisLabel: { formatter: "{value}%", color: CHART.axis, fontSize: 11 },
    splitLine: { lineStyle: { color: CHART.grid, type: "dashed" as const } },
    axisLine: { show: false },
    ...extra,
  };
}

export function axisValuePlain(extra: Record<string, unknown> = {}) {
  return {
    type: "value" as const,
    axisLabel: { color: CHART.axis, fontSize: 11 },
    splitLine: { lineStyle: { color: CHART.grid, type: "dashed" as const } },
    axisLine: { show: false },
    ...extra,
  };
}

export function legendBase(extra: Record<string, unknown> = {}) {
  return {
    top: 8,
    left: 0,
    itemWidth: 16,
    itemHeight: 8,
    textStyle: { color: CHART.muted, fontSize: 12 },
    ...extra,
  };
}

export function zeroMarkLine() {
  return {
    symbol: "none" as const,
    label: { show: false },
    data: [{ yAxis: 0, lineStyle: { color: CHART.zero, type: "dashed" as const, width: 1 } }],
  };
}

export function areaGradient(hex: string, alphaTop = 0.28) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return {
    type: "linear" as const,
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      { offset: 0, color: `rgba(${r},${g},${b},${alphaTop})` },
      { offset: 1, color: `rgba(${r},${g},${b},0)` },
    ],
  };
}

export function chartCardClass() {
  return "rounded-2xl border border-slate-200/90 bg-gradient-to-br from-sky-50/40 via-white to-amber-50/30 p-5 shadow-sm";
}
