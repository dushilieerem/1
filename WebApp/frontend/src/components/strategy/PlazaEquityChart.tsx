import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import {
  areaGradient,
  axisCategory,
  axisValuePct,
  darkTooltip,
  legendBase,
} from "@/components/chartTheme";
import {
  curveToCumPct,
  type PlazaCurvePoint,
} from "@/lib/strategyPlazaApi";

/** 广场图配色：红策略 / 琥珀超额 / 蓝基准 */
export const PLAZA_CHART = {
  strategy: "#ef4444",
  excess: "#f59e0b",
  bench: "#3b82f6",
  grid: "#e2e8f0",
  axis: "#64748b",
} as const;

type Props = {
  equity?: PlazaCurvePoint[] | null;
  benchmark?: PlazaCurvePoint[] | null;
  height?: number;
  compact?: boolean;
  showExcess?: boolean;
};

function fmtAxisDate(d: string) {
  if (/^\d{4}-\d{2}-\d{2}/.test(d)) return d.slice(2, 10);
  return d;
}

/** 广场收益图：日期横轴 + 悬停 tooltip */
export function PlazaEquityChart({
  equity,
  benchmark,
  height = 220,
  compact = false,
  showExcess = true,
}: Props) {
  const option = useMemo(() => {
    const strat = curveToCumPct(equity);
    const benchMap = new Map(
      (benchmark || [])
        .filter((p) => p?.date && typeof p.value === "number")
        .map((p) => [p.date, p.value]),
    );
    const benchPts = (benchmark || [])
      .filter((p) => p?.date && typeof p.value === "number")
      .slice()
      .sort((a, b) => String(a.date).localeCompare(String(b.date)));
    const benchBase = benchPts[0]?.value ?? 1;
    const benchAligned: (number | null)[] = strat.dates.map((d) => {
      const v = benchMap.get(d);
      return v != null && Number.isFinite(v)
        ? ((v / benchBase) - 1) * 100
        : null;
    });
    const hasBench = benchAligned.some((v) => v != null);
    const excess =
      showExcess && hasBench
        ? strat.values.map((s, i) => {
            const b = benchAligned[i];
            return b == null ? null : s - b;
          })
        : null;

    const n = strat.dates.length;
    const tickCount = compact ? 4 : 5;

    const series: Record<string, unknown>[] = [
      {
        name: "策略",
        type: "line",
        data: strat.values,
        showSymbol: false,
        smooth: 0.2,
        triggerLineEvent: true,
        lineStyle: { width: compact ? 1.8 : 2.2, color: PLAZA_CHART.strategy },
        areaStyle: { color: areaGradient(PLAZA_CHART.strategy, 0.22) },
        z: 3,
      },
    ];
    if (hasBench) {
      series.push({
        name: "基准",
        type: "line",
        data: benchAligned,
        showSymbol: false,
        smooth: 0.15,
        lineStyle: { width: compact ? 1.2 : 1.5, color: PLAZA_CHART.bench },
        z: 2,
      });
    }
    if (excess) {
      series.push({
        name: "超额",
        type: "line",
        data: excess,
        showSymbol: false,
        smooth: 0.15,
        lineStyle: { width: compact ? 1 : 1.4, color: PLAZA_CHART.excess },
        z: 1,
      });
    }

    return {
      animationDuration: 650,
      color: [PLAZA_CHART.strategy, PLAZA_CHART.bench, PLAZA_CHART.excess],
      grid: {
        left: compact ? 40 : 48,
        right: compact ? 14 : 18,
        top: compact ? 24 : 36,
        bottom: compact ? 32 : 40,
      },
      legend: compact
        ? { show: false }
        : {
            ...legendBase(),
            top: 2,
            data: series.map((s) => String(s.name)),
          },
      tooltip: {
        ...darkTooltip(),
        trigger: "axis",
        // ECharts 6：挂到 body，避免卡片裁切 / 叠层挡住
        appendTo: "body",
        confine: false,
        axisPointer: {
          type: "line",
          lineStyle: { color: "#94a3b8", width: 1, type: "dashed" },
        },
        formatter: (params: unknown) => {
          const arr = (Array.isArray(params) ? params : [params]) as Array<{
            axisValue?: string;
            dataIndex?: number;
            marker?: string;
            seriesName?: string;
            value?: number | null;
            data?: number | null;
          }>;
          if (!arr.length) return "";
          const first = arr[0];
          const date =
            first?.axisValue != null
              ? String(first.axisValue)
              : strat.dates[first?.dataIndex ?? 0] || "";
          const lines = [
            `<div style="margin-bottom:6px;font-weight:600">${date}</div>`,
          ];
          for (const p of arr) {
            const v = p.value ?? p.data;
            const txt =
              v == null || Number.isNaN(Number(v))
                ? "—"
                : `${Number(v).toFixed(2)}%`;
            lines.push(
              `<div style="margin:2px 0">${p.marker || ""}${p.seriesName || ""}&nbsp;&nbsp;<b>${txt}</b></div>`,
            );
          }
          return lines.join("");
        },
      },
      xAxis: axisCategory({
        data: strat.dates,
        axisLabel: {
          color: PLAZA_CHART.axis,
          fontSize: compact ? 10 : 11,
          formatter: (v: string) => fmtAxisDate(String(v)),
          interval: Math.max(0, Math.floor((n - 1) / Math.max(tickCount - 1, 1))),
          hideOverlap: true,
          showMinLabel: true,
          showMaxLabel: true,
        },
      }),
      yAxis: {
        ...axisValuePct(),
        splitLine: {
          lineStyle: { color: PLAZA_CHART.grid, type: "dashed" },
        },
      },
      series,
    };
  }, [equity, benchmark, compact, showExcess]);

  if (!(equity || []).length) {
    return (
      <div
        className="flex items-center justify-center rounded-xl bg-slate-50 text-sm text-slate-400"
        style={{ height }}
      >
        暂无收益曲线
      </div>
    );
  }

  return (
    <ReactECharts
      option={option}
      style={{ height, width: "100%" }}
      opts={{ renderer: "canvas" }}
      notMerge
      lazyUpdate={false}
    />
  );
}
