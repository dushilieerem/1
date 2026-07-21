import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import {
  CHART,
  areaGradient,
  axisCategory,
  axisValuePlain,
  chartCardClass,
  darkTooltip,
  zeroMarkLine,
} from "@/components/chartTheme";
import type { YgFactorAnalysis, YgSeriesPoint } from "@/lib/ygApi";

type Props = {
  fa: YgFactorAnalysis | null | undefined;
};

function icMetrics(series: YgSeriesPoint[], fa: YgFactorAnalysis | null | undefined) {
  const vals = series.map((p) => p.value).filter((v) => Number.isFinite(v));
  const mean =
    typeof fa?.ic_mean === "number" && Number.isFinite(fa.ic_mean)
      ? fa.ic_mean
      : vals.length
        ? vals.reduce((s, v) => s + v, 0) / vals.length
        : 0;
  const std =
    typeof fa?.ic_std === "number" && Number.isFinite(fa.ic_std)
      ? fa.ic_std
      : vals.length > 1
        ? Math.sqrt(vals.reduce((s, v) => s + (v - mean) ** 2, 0) / vals.length)
        : 0;
  const ir = std > 1e-12 ? mean / std : 0;
  const posPct = vals.length ? (100 * vals.filter((v) => v > 0).length) / vals.length : 0;
  return { mean, std, ir, posPct };
}

const METRIC_CARDS = [
  { key: "mean", label: "IC 均值", fmt: (v: number) => v.toFixed(4) },
  { key: "std", label: "IC 波动", fmt: (v: number) => v.toFixed(4) },
  { key: "ir", label: "IR", fmt: (v: number) => v.toFixed(2) },
  { key: "posPct", label: "IC > 0", fmt: (v: number) => `${v.toFixed(1)}%` },
] as const;

/** 均值虚线：只画线，文案放到卡片右上角 */
function meanDashLine(y: number) {
  return {
    symbol: "none" as const,
    silent: true,
    label: { show: false },
    data: [{ yAxis: y, lineStyle: { color: CHART.amber, type: "dashed" as const, width: 1.3 } }],
  };
}

export function ICDetectPanel({ fa }: Props) {
  const series = fa?.ic_series || [];
  const cumSeries = fa?.cumulative_ic_series || [];
  const irSeries = fa?.rolling_ir_series || [];
  const metrics = useMemo(() => icMetrics(series, fa), [series, fa]);

  const periodOpt = useMemo(() => {
    if (!series.length) return null;
    const dates = series.map((p) => p.date);
    const vals = series.map((p) => p.value);
    return {
      grid: { left: 52, right: 16, top: 20, bottom: 40 },
      tooltip: {
        ...darkTooltip(),
        formatter: (params: Array<{ value: number; axisValue: string; marker: string }>) => {
          const p = params[0];
          if (!p) return "";
          return `<b>${p.axisValue}</b><br/>${p.marker} IC: ${Number(p.value).toFixed(4)}`;
        },
      },
      xAxis: axisCategory({ data: dates }),
      yAxis: {
        ...axisValuePlain({ scale: true, name: "IC", nameTextStyle: { color: CHART.axis, fontSize: 11 } }),
      },
      dataZoom: [{ type: "inside" as const }],
      series: [
        {
          name: "IC",
          type: "line" as const,
          showSymbol: false,
          lineStyle: { width: 1.2, color: "#3b82f6" },
          itemStyle: { color: "#3b82f6" },
          data: vals,
          markLine: meanDashLine(metrics.mean),
        },
      ],
    };
  }, [series, metrics.mean]);

  const cumOpt = useMemo(() => {
    if (!cumSeries.length) return null;
    const dates = cumSeries.map((p) => p.date);
    const vals = cumSeries.map((p) => p.value);
    return {
      grid: { left: 52, right: 16, top: 20, bottom: 40 },
      tooltip: {
        ...darkTooltip(),
        formatter: (params: Array<{ value: number; axisValue: string; marker: string }>) => {
          const p = params[0];
          if (!p) return "";
          return `<b>${p.axisValue}</b><br/>${p.marker} 累计 IC: ${Number(p.value).toFixed(4)}`;
        },
      },
      xAxis: axisCategory({ data: dates }),
      yAxis: {
        ...axisValuePlain({
          scale: true,
          name: "累计 IC",
          nameTextStyle: { color: CHART.axis, fontSize: 11 },
        }),
      },
      dataZoom: [{ type: "inside" as const }],
      series: [
        {
          name: "累计 IC",
          type: "line" as const,
          showSymbol: false,
          lineStyle: { width: 2, color: "#16a34a" },
          itemStyle: { color: "#16a34a" },
          areaStyle: { color: areaGradient("#16a34a", 0.12) },
          data: vals,
          markLine: zeroMarkLine(),
        },
      ],
    };
  }, [cumSeries]);

  const histOpt = useMemo(() => {
    const raw = series.map((p) => p.value).filter((v) => Number.isFinite(v));
    if (!raw.length) return null;
    const min = Math.min(...raw);
    const max = Math.max(...raw);
    const bins = 24;
    const span = Math.max(max - min, 1e-9);
    const step = span / bins;
    const counts = new Array<number>(bins).fill(0);
    for (const v of raw) {
      const idx = Math.min(bins - 1, Math.floor((v - min) / step));
      counts[idx] += 1;
    }
    const centers = counts.map((_, i) => min + (i + 0.5) * step);
    // 横轴只标约 6 个刻度，避免挤在一起
    const labelEvery = Math.max(1, Math.ceil(bins / 6));
    return {
      grid: { left: 52, right: 16, top: 20, bottom: 44 },
      tooltip: {
        ...darkTooltip(),
        formatter: (p: { dataIndex: number; value: number; marker: string }) => {
          const c = centers[p.dataIndex];
          return `IC ≈ ${c.toFixed(4)}<br/>${p.marker} 频数: ${p.value}`;
        },
      },
      xAxis: {
        type: "category" as const,
        data: centers.map((c) => c.toFixed(3)),
        name: "IC",
        nameLocation: "middle" as const,
        nameGap: 26,
        nameTextStyle: { color: CHART.axis, fontSize: 11 },
        axisLabel: {
          color: CHART.axis,
          fontSize: 10,
          rotate: 0,
          interval: (idx: number) => idx % labelEvery === 0,
        },
        axisLine: { lineStyle: { color: CHART.grid } },
        axisTick: { show: false },
      },
      yAxis: {
        ...axisValuePlain({
          name: "频数",
          nameTextStyle: { color: CHART.axis, fontSize: 11 },
        }),
      },
      series: [
        {
          name: "频数",
          type: "bar" as const,
          data: counts,
          barMaxWidth: 14,
          itemStyle: {
            color: "#8b5cf6",
            borderRadius: [2, 2, 0, 0],
          },
          // 均值只用细虚线，不改柱色、不贴字
          markLine: {
            symbol: "none",
            silent: true,
            label: { show: false },
            data: [
              {
                xAxis: centers[Math.min(bins - 1, Math.max(0, Math.floor((metrics.mean - min) / step)))].toFixed(3),
                lineStyle: { color: CHART.amber, type: "dashed" as const, width: 1.3 },
              },
            ],
          },
        },
      ],
    };
  }, [series, metrics.mean]);

  const irOpt = useMemo(() => {
    let dates: string[] = [];
    let vals: (number | null)[] = [];
    if (irSeries.length) {
      dates = irSeries.map((p) => p.date);
      vals = irSeries.map((p) => (Number.isFinite(p.value) ? p.value : null));
    } else if (series.length) {
      dates = series.map((p) => p.date);
      const raw = series.map((p) => p.value);
      const windowSize = 60;
      vals = raw.map((_, i) => {
        const start = Math.max(0, i - windowSize + 1);
        const arr = raw.slice(start, i + 1).filter((v) => Number.isFinite(v));
        if (arr.length < 10) return null;
        const mean = arr.reduce((s, v) => s + v, 0) / arr.length;
        const variance = arr.reduce((s, v) => s + (v - mean) ** 2, 0) / arr.length;
        const std = Math.sqrt(variance);
        return std > 1e-12 ? mean / std : null;
      });
    } else {
      return null;
    }
    return {
      grid: { left: 52, right: 16, top: 20, bottom: 40 },
      tooltip: {
        ...darkTooltip(),
        formatter: (params: Array<{ value: number | null; axisValue: string; marker: string }>) => {
          const p = params[0];
          if (!p || p.value == null) return "";
          return `<b>${p.axisValue}</b><br/>${p.marker} IR: ${Number(p.value).toFixed(4)}`;
        },
      },
      xAxis: axisCategory({ data: dates }),
      yAxis: {
        ...axisValuePlain({ scale: true, name: "IR", nameTextStyle: { color: CHART.axis, fontSize: 11 } }),
      },
      dataZoom: [{ type: "inside" as const }],
      series: [
        {
          name: "滚动 IR(60)",
          type: "line" as const,
          showSymbol: false,
          lineStyle: { width: 1.8, color: "#ef4444" },
          itemStyle: { color: "#ef4444" },
          areaStyle: { color: areaGradient("#ef4444", 0.1) },
          data: vals,
          markLine: zeroMarkLine(),
        },
      ],
    };
  }, [irSeries, series]);

  if (!series.length && !cumSeries.length) {
    return (
      <div className="flex h-80 items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-500">
        暂无 IC 序列（请重新跑一次检测）
      </div>
    );
  }

  const metricMap = {
    mean: metrics.mean,
    std: metrics.std,
    ir: metrics.ir,
    posPct: metrics.posPct,
  };

  const panels: { title: string; option: object | null; badge?: string }[] = [
    { title: "日频 IC", option: periodOpt, badge: `均值 ${metrics.mean.toFixed(4)}` },
    { title: "累计 IC", option: cumOpt },
    { title: "IC 分布", option: histOpt, badge: `均值 ${metrics.mean.toFixed(4)}` },
    { title: "滚动 IR（60日）", option: irOpt },
  ];

  return (
    <section className={chartCardClass()}>
      <h2 className="mb-4 text-lg font-bold tracking-tight text-slate-900">IC 分析</h2>

      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {METRIC_CARDS.map(({ key, label, fmt }) => (
          <div
            key={key}
            className="rounded-xl border border-slate-200/80 bg-gradient-to-b from-slate-50 to-white px-3 py-3 text-center shadow-sm"
          >
            <p className="text-[10px] font-medium uppercase tracking-wide text-slate-400">{label}</p>
            <p className="mt-1 font-mono text-lg font-bold text-slate-900">{fmt(metricMap[key])}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {panels.map((panel) => (
          <div key={panel.title} className="rounded-xl border border-slate-200/80 bg-white p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <p className="text-sm font-semibold text-slate-800">{panel.title}</p>
              {panel.badge ? (
                <span className="shrink-0 rounded-md bg-amber-50 px-2 py-0.5 font-mono text-[11px] font-medium text-amber-700">
                  {panel.badge}
                </span>
              ) : null}
            </div>
            {panel.option ? (
              <ReactECharts option={panel.option} style={{ height: 280 }} notMerge lazyUpdate opts={{ renderer: "canvas" }} />
            ) : (
              <p className="flex h-[280px] items-center justify-center text-sm text-slate-400">暂无数据</p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
