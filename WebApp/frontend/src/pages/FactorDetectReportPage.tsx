import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import {
  Activity,
  BarChart3,
  Building2,
  Clock,
  Layers,
  LineChart,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import {
  CHART,
  QUANTILE_PALETTE,
  areaGradient,
  axisCategory,
  axisValuePct,
  chartCardClass,
  darkTooltip,
  legendBase,
} from "@/components/chartTheme";
import { ICDetectPanel } from "@/components/factor/ICDetectPanel";
import { IndustryDetectPanel } from "@/components/factor/IndustryDetectPanel";
import {
  DETECT_BENCHMARK_OPTIONS,
  DETECT_UNIVERSE_OPTIONS,
  getRun,
  loadLastResult,
  optionLabel,
  peekRun,
  type DetectRunRecord,
} from "@/lib/detectStore";

type ReportTab = "equity" | "groups" | "ic" | "industry" | "overview";

const NAV: { id: ReportTab; label: string; icon: typeof LineChart }[] = [
  { id: "equity", label: "累计收益与回撤", icon: TrendingDown },
  { id: "groups", label: "分组累计收益", icon: LineChart },
  { id: "ic", label: "IC", icon: Activity },
  { id: "industry", label: "行业", icon: Building2 },
  { id: "overview", label: "绩效概览", icon: BarChart3 },
];

const CORE_TABS: ReportTab[] = ["equity", "groups", "overview"];

function hasIcData(rec: DetectRunRecord | null | undefined): boolean {
  const fa = rec?.result?.factor_analysis;
  if (!fa) return false;
  return Boolean(
    (fa.ic_series && fa.ic_series.length) ||
      (fa.cumulative_ic_series && fa.cumulative_ic_series.length) ||
      (fa.rolling_ir_series && fa.rolling_ir_series.length) ||
      fa.ic_mean != null ||
      fa.rank_ic_mean != null,
  );
}

function hasIndustryData(rec: DetectRunRecord | null | undefined): boolean {
  const fa = rec?.result?.factor_analysis;
  if (!fa) return false;
  return Boolean(
    (fa.industry_equity_curves && fa.industry_equity_curves.length) ||
      (fa.industry_group_equity_curves && fa.industry_group_equity_curves.length),
  );
}

function visibleNavFor(rec: DetectRunRecord | null | undefined) {
  const level = rec?.request?.analysis_level;
  if (level === "core") {
    return NAV.filter((n) => CORE_TABS.includes(n.id));
  }
  // full 或旧数据未带 analysis_level：按结果字段显隐 IC / 行业
  return NAV.filter((n) => {
    if (n.id === "ic") return hasIcData(rec);
    if (n.id === "industry") return hasIndustryData(rec);
    return true;
  });
}
function pct(x?: number | null) {
  if (x == null || Number.isNaN(x)) return "—";
  return `${(x * 100).toFixed(2)}%`;
}
function num(x?: number | null) {
  if (x == null || Number.isNaN(x)) return "—";
  return x.toFixed(3);
}
function toCumPct(nav: number) {
  return (nav - 1) * 100;
}

function layeredEntries(lr: Record<string, number | null> | undefined | null) {
  if (!lr || typeof lr !== "object") return [] as { key: string; label: string; value: number }[];
  const out: { key: string; label: string; value: number }[] = [];
  for (const [k, v] of Object.entries(lr)) {
    if (!/^layer\d+$/i.test(k)) continue;
    if (typeof v !== "number" || Number.isNaN(v)) continue;
    const n = k.replace(/layer/i, "");
    out.push({ key: k, label: `Q${n}`, value: v });
  }
  out.sort((a, b) => a.key.localeCompare(b.key, undefined, { numeric: true }));
  return out;
}

function zoomSlider() {
  return [
    { type: "inside" as const },
    {
      type: "slider" as const,
      height: 18,
      bottom: 8,
      borderColor: CHART.grid,
      fillerColor: "rgba(13,148,136,0.12)",
      handleStyle: { color: CHART.ink },
    },
  ];
}

/** 图例右上；grid.top 留空，MDD 横标在竖线顶端（低于图例） */
function legendTopRight(data: string[]) {
  return {
    ...legendBase({ top: 4, right: 8, left: "auto" }),
    data,
  };
}

/** MDD：竖线居中横写「MDD」，贴在图区顶部（在右上图例下方） */
function mddMarkLine(troughDate: string) {
  return {
    symbol: "none" as const,
    silent: true,
    data: [
      {
        xAxis: troughDate,
        lineStyle: { color: CHART.amber, type: "dashed" as const, width: 1.5 },
        label: {
          show: true,
          formatter: "MDD",
          position: "end" as const,
          rotate: 0,
          distance: 10,
          color: CHART.amber,
          fontSize: 12,
          fontWeight: 700 as const,
          backgroundColor: "rgba(255,255,255,0.92)",
          padding: [2, 6] as [number, number],
          borderRadius: 3,
        },
      },
    ],
  };
}

export function FactorDetectReportPage() {
  const { runId = "" } = useParams();
  const [rec, setRec] = useState<DetectRunRecord | null | undefined>(() =>
    runId ? peekRun(runId) ?? undefined : undefined,
  );
  const [tab, setTab] = useState<ReportTab>("equity");

  useEffect(() => {
    let cancelled = false;
    const cached = peekRun(runId);
    if (cached) setRec(cached);
    else setRec(undefined);
    (async () => {
      const byId = await getRun(runId);
      if (cancelled) return;
      if (byId) {
        setRec(byId);
        return;
      }
      const last = await loadLastResult();
      if (cancelled) return;
      if (last && (last.id === runId || last.factorName === runId)) setRec(last);
      else setRec(null);
    })();
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const visibleNav = useMemo(() => visibleNavFor(rec), [rec]);

  useEffect(() => {
    if (!visibleNav.some((n) => n.id === tab)) {
      setTab(visibleNav[0]?.id || "equity");
    }
  }, [visibleNav, tab]);

  const result = rec?.result;
  const m = result?.metrics;
  const req = rec?.request;
  const groups =
    Number(result?.factor_analysis?.layered_returns?.groups) ||
    Number(req?.groups) ||
    5;

  const curveDates = useMemo(() => result?.equity_curve?.map((p) => p.date) || [], [result]);
  const stratPct = useMemo(
    () => (result?.equity_curve || []).map((p) => toCumPct(p.value)),
    [result],
  );
  const benchPct = useMemo(() => {
    const c = result?.equity_curve;
    if (!c?.length) return [] as (number | null)[];
    const benchMap = new Map((result?.benchmark_curve || []).map((p) => [p.date, p.value]));
    return c.map((p) => {
      const bv = benchMap.get(p.date);
      return bv == null ? null : toCumPct(bv);
    });
  }, [result]);
  const ddPct = useMemo(
    () => (result?.equity_curve || []).map((p) => (p.drawdown ?? 0) * 100),
    [result],
  );
  const hasBench = benchPct.some((v) => v != null);

  const mddMeta = useMemo(() => {
    const curve = result?.equity_curve || [];
    const fromMetric = result?.metrics?.max_drawdown;
    const mddPct =
      typeof fromMetric === "number" && !Number.isNaN(fromMetric)
        ? fromMetric * 100
        : ddPct.length
          ? Math.min(...ddPct)
          : 0;

    // 两图统一：标在「回撤最深」那天（谷底），与红横线一致
    let troughDate: string | null = null;
    if (curve.length) {
      let best = 0;
      let idx = -1;
      curve.forEach((p, i) => {
        const d = p.drawdown ?? 0;
        if (d < best) {
          best = d;
          idx = i;
        }
      });
      if (idx >= 0) troughDate = curve[idx].date;
    }
    if (!troughDate) {
      const dds = result?.drawdowns || [];
      const worst = [...dds].sort((a, b) => (a.depth ?? 0) - (b.depth ?? 0))[0];
      troughDate = worst?.end || null;
    }
    return { mddPct, troughDate };
  }, [result, ddPct]);

  /** 上行：策略 vs 基准；橙虚线 MDD = 最大回撤谷底日（与下图对齐） */
  const equityOnlyOpt = useMemo(() => {
    if (!curveDates.length) return null;
    return {
      color: [CHART.ink, CHART.bench],
      tooltip: {
        ...darkTooltip(),
        formatter: (params: Array<{ seriesName: string; value: number | null; axisValue: string; marker: string }>) => {
          const head = params[0]?.axisValue ?? "";
          const rows = params
            .filter((p) => p.value != null && !Number.isNaN(Number(p.value)))
            .map((p) => `${p.marker} ${p.seriesName}: ${Number(p.value).toFixed(2)}%`)
            .join("<br/>");
          return `<b>${head}</b><br/>${rows}`;
        },
      },
      legend: legendTopRight(hasBench ? ["策略", "基准"] : ["策略"]),
      grid: { left: 52, right: 20, top: 48, bottom: 52 },
      dataZoom: zoomSlider(),
      xAxis: axisCategory({
        data: curveDates,
        boundaryGap: false,
        axisLabel: { color: CHART.axis, fontSize: 11, hideOverlap: true },
      }),
      yAxis: { ...axisValuePct(), scale: true },
      series: [
        {
          name: "策略",
          type: "line",
          smooth: 0.25,
          showSymbol: false,
          data: stratPct,
          lineStyle: { width: 2.2, color: CHART.ink },
          areaStyle: { color: areaGradient(CHART.ink, 0.14) },
          itemStyle: { color: CHART.ink },
          markLine: mddMeta.troughDate ? mddMarkLine(mddMeta.troughDate) : undefined,
        },
        ...(hasBench
          ? [
              {
                name: "基准",
                type: "line" as const,
                smooth: 0.25,
                showSymbol: false,
                data: benchPct,
                lineStyle: { width: 2, color: CHART.bench },
                itemStyle: { color: CHART.bench },
              },
            ]
          : []),
      ],
    };
  }, [curveDates, stratPct, benchPct, hasBench, mddMeta.troughDate]);

  /** 下行：水平线 = MDD 深度；橙色竖线 = 谷底日 */
  const drawdownOnlyOpt = useMemo(() => {
    if (!curveDates.length) return null;
    return {
      color: [CHART.amber],
      tooltip: {
        ...darkTooltip(),
        formatter: (params: Array<{ value: number; axisValue: string; marker: string }>) => {
          const p = params[0];
          if (!p) return "";
          return `<b>${p.axisValue}</b><br/>${p.marker} 回撤: ${Number(p.value).toFixed(2)}%`;
        },
      },
      legend: legendTopRight(["回撤"]),
      grid: { left: 52, right: 28, top: 48, bottom: 52 },
      dataZoom: zoomSlider(),
      xAxis: axisCategory({
        data: curveDates,
        boundaryGap: false,
        axisLabel: { color: CHART.axis, fontSize: 11, hideOverlap: true },
      }),
      yAxis: {
        ...axisValuePct(),
        max: 0,
        scale: true,
      },
      series: [
        {
          name: "回撤",
          type: "line",
          smooth: true,
          showSymbol: false,
          data: ddPct,
          lineStyle: { width: 1.2, color: CHART.amber },
          areaStyle: { color: areaGradient(CHART.amber, 0.4) },
          itemStyle: { color: CHART.amber },
          markLine: {
            symbol: "none",
            silent: true,
            data: [
              {
                yAxis: mddMeta.mddPct,
                lineStyle: { color: "#e11d48", type: "solid", width: 1.8 },
                label: { show: false },
              },
              ...(mddMeta.troughDate ? mddMarkLine(mddMeta.troughDate).data : []),
            ],
          },
        },
      ],
    };
  }, [curveDates, ddPct, mddMeta]);

  const groupCumOpt = useMemo(() => {
    const seriesPts = result?.factor_analysis?.cumulative_series;
    if (!seriesPts?.length) return null;
    const n = Math.min(Math.max(groups, 1), 5);
    const groupKeys = Array.from({ length: n }, (_, i) => `layer${i + 1}`);
    const benchMap = new Map((result?.benchmark_curve || []).map((p) => [p.date, p.value]));
    const dates = seriesPts.map((p) => String(p.date));
    const showBench = dates.some((d) => benchMap.has(d));

    return {
      color: showBench ? [CHART.bench, ...QUANTILE_PALETTE] : [...QUANTILE_PALETTE],
      grid: { left: 52, right: 20, top: 40, bottom: 56 },
      tooltip: {
        ...darkTooltip(),
        formatter: (params: Array<{ seriesName: string; value: number | null; axisValue: string; marker: string }>) => {
          const head = params[0]?.axisValue ?? "";
          const rows = params
            .filter((p) => p.value != null && !Number.isNaN(Number(p.value)))
            .map((p) => `${p.marker} ${p.seriesName}: ${Number(p.value).toFixed(2)}%`)
            .join("<br/>");
          return `<b>${head}</b><br/>${rows}`;
        },
      },
      legend: legendTopRight(showBench ? ["基准", ...groupKeys.map((_, i) => `Q${i + 1}`)] : groupKeys.map((_, i) => `Q${i + 1}`)),
      xAxis: axisCategory({ data: dates }),
      yAxis: axisValuePct(),
      dataZoom: zoomSlider(),
      series: [
        ...(showBench
          ? [
              {
                name: "基准",
                type: "line" as const,
                smooth: true,
                symbol: "none" as const,
                z: 1,
                lineStyle: { width: 2.5, color: CHART.bench },
                areaStyle: { color: areaGradient("#334155", 0.1) },
                data: dates.map((d) => {
                  const v = benchMap.get(d);
                  return v == null ? null : toCumPct(v);
                }),
              },
            ]
          : []),
        ...groupKeys.map((k, i) => ({
          name: `Q${i + 1}`,
          type: "line" as const,
          smooth: true,
          symbol: "none" as const,
          z: 2 + i,
          lineStyle: { width: 2.2, color: QUANTILE_PALETTE[i % QUANTILE_PALETTE.length] },
          data: seriesPts.map((p) => {
            const v = p[k];
            return typeof v === "number" ? toCumPct(v) : null;
          }),
        })),
      ],
    };
  }, [result, groups]);

  const annualOpt = useMemo(() => {
    const rows = result?.annual_returns;
    if (!rows?.length) return null;
    const vals = rows.map((r) => (r.return_value ?? 0) * 100);
    return {
      tooltip: {
        ...darkTooltip(),
        trigger: "item",
        formatter: (p: { dataIndex: number; value: number | { value: number }; marker: string }) => {
          const row = rows[p.dataIndex];
          if (!row) return "";
          const raw = typeof p.value === "number" ? p.value : p.value?.value;
          return `<b>${row.year}</b><br/>${p.marker} 年化收益: ${Number(raw).toFixed(2)}%`;
        },
      },
      grid: { left: 16, right: 16, top: 28, bottom: 28, containLabel: true },
      xAxis: {
        type: "category",
        data: rows.map((r) => String(r.year)),
        axisLine: { lineStyle: { color: CHART.grid } },
        axisLabel: { color: CHART.axis, fontSize: 11 },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        axisLabel: { formatter: "{value}%", color: CHART.axis, fontSize: 11 },
        splitLine: { lineStyle: { color: CHART.grid, type: "dashed" } },
        axisLine: { show: false },
      },
      series: [
        {
          type: "bar",
          barMaxWidth: 36,
          data: vals.map((v) => ({
            value: v,
            itemStyle: { color: v >= 0 ? CHART.positive : CHART.negative, borderRadius: [4, 4, 0, 0] },
          })),
        },
      ],
    };
  }, [result]);

  const layers = useMemo(() => layeredEntries(result?.factor_analysis?.layered_returns), [result]);
  const layerOpt = useMemo(() => {
    if (!layers.length) return null;
    const vals = layers.map((x) => x.value * 100);
    return {
      tooltip: {
        ...darkTooltip(),
        trigger: "item",
        formatter: (p: { dataIndex: number; value: number | { value: number }; marker: string }) => {
          const layer = layers[p.dataIndex];
          if (!layer) return "";
          const raw = typeof p.value === "number" ? p.value : p.value?.value;
          return `<b>${layer.label}</b><br/>${p.marker} 分层收益: ${Number(raw).toFixed(2)}%`;
        },
      },
      grid: { left: 16, right: 16, top: 28, bottom: 28, containLabel: true },
      xAxis: {
        type: "category",
        data: layers.map((x) => x.label),
        axisLine: { lineStyle: { color: CHART.grid } },
        axisLabel: { color: CHART.axis, fontSize: 11 },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        axisLabel: { formatter: "{value}%", color: CHART.axis, fontSize: 11 },
        splitLine: { lineStyle: { color: CHART.grid, type: "dashed" } },
        axisLine: { show: false },
      },
      series: [
        {
          type: "bar",
          barMaxWidth: 40,
          data: vals.map((v, i) => ({
            value: v,
            itemStyle: {
              color: QUANTILE_PALETTE[i % QUANTILE_PALETTE.length],
              borderRadius: [4, 4, 0, 0],
            },
          })),
        },
      ],
    };
  }, [layers]);

  if (rec === undefined) {
    return <div className="mx-auto max-w-lg px-6 py-20 text-center text-slate-400">加载中…</div>;
  }

  if (!rec) {
    return (
      <div className="mx-auto max-w-lg px-6 py-20 text-center">
        <p className="text-slate-600">没有找到检测结果，请先运行检测。</p>
        <Link to="/factor/detect" className="mt-4 inline-block text-sm font-medium text-blue-600 underline">
          返回检测列表
        </Link>
      </div>
    );
  }

  const dds = result?.drawdowns || [];
  const spread = result?.factor_analysis?.layered_returns?.spread;
  const rangeLabel =
    req?.start && req?.end
      ? `${req.start} ~ ${req.end}`
      : result?.date_range?.start && result?.date_range?.end
        ? `${result.date_range.start} ~ ${result.date_range.end}`
        : "—";

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-gradient-to-b from-slate-50 to-white">
      {/* 顶栏：标题 + 元信息卡片（对齐 NBQuant） */}
      <div className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-3 px-6 py-3">
          <div>
            <p className="text-sm text-slate-500">
              <Link to="/factor/detect" className="hover:text-blue-600">
                因子检测
              </Link>
              {" / "}
              <Link to={`/factor/detect/${rec.projectId}`} className="hover:text-blue-600">
                {rec.description}
              </Link>
              {" / 检测报告"}
            </p>
            <h1 className="mt-0.5 text-lg font-bold text-slate-900">{rec.description}</h1>
            <p className="font-mono text-xs text-slate-500">{rec.factorName}</p>
          </div>
          <Link
            to={`/factor/detect/${rec.projectId}/history`}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
          >
            检测列表
          </Link>
        </div>

        <div className="mx-auto grid max-w-[1400px] grid-cols-2 gap-2 px-6 pb-3 sm:grid-cols-3 lg:grid-cols-5">
          <MetaChip icon={<Clock className="h-3.5 w-3.5 text-blue-500" />} label="区间" value={rangeLabel} />
          <MetaChip
            icon={<Layers className="h-3.5 w-3.5 text-amber-500" />}
            label="股票池"
            value={optionLabel(req?.universe || "", DETECT_UNIVERSE_OPTIONS)}
          />
          <MetaChip
            icon={<TrendingUp className="h-3.5 w-3.5 text-teal-500" />}
            label="基准"
            value={optionLabel(req?.benchmark || "", DETECT_BENCHMARK_OPTIONS)}
          />
          <MetaChip
            icon={
              <div className="flex h-3.5 w-3.5 items-center justify-center rounded bg-blue-100 text-[9px] font-bold text-blue-600">
                {groups}
              </div>
            }
            label="分组 · 调仓"
            value={`${groups} 组 · ${req?.rebalance_days ?? "—"} 日`}
          />
          <MetaChip
            icon={<BarChart3 className="h-3.5 w-3.5 text-slate-500" />}
            label="运行耗时"
            value={`${rec.elapsedSec}s`}
          />
        </div>
      </div>

      <div className="mx-auto max-w-[1400px] px-6 py-5">
        {/* 移动端顶栏导航 */}
        <nav className="mb-4 flex gap-1 overflow-x-auto border-b border-slate-200 pb-2 lg:hidden">
          {visibleNav.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              className={`shrink-0 rounded-full px-3 py-1.5 text-xs ${
                tab === item.id ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-600"
              }`}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="flex gap-6">
          {/* 左侧导航（两行以上菜单项） */}
          <aside className="hidden w-44 shrink-0 lg:block">
            <nav className="sticky top-20 space-y-0.5">
              {visibleNav.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setTab(item.id)}
                  className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition ${
                    tab === item.id
                      ? "bg-blue-50 font-medium text-blue-700 ring-1 ring-blue-100"
                      : "text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  <item.icon className="h-4 w-4 shrink-0" />
                  {item.label}
                </button>
              ))}
            </nav>
          </aside>

          <main className="min-w-0 flex-1">
            {tab === "equity" && (
              <div className="space-y-5">
                <section className={chartCardClass()}>
                  <h2 className="mb-2 text-lg font-bold tracking-tight text-slate-900">累计收益</h2>
                  {equityOnlyOpt ? (
                    <ReactECharts option={equityOnlyOpt} style={{ height: 320 }} notMerge opts={{ renderer: "canvas" }} />
                  ) : (
                    <p className="py-16 text-center text-sm text-slate-400">暂无净值数据</p>
                  )}
                </section>

                <section className={chartCardClass()}>
                  <h2 className="mb-2 text-lg font-bold tracking-tight text-slate-900">动态回撤</h2>
                  {drawdownOnlyOpt ? (
                    <ReactECharts option={drawdownOnlyOpt} style={{ height: 240 }} notMerge opts={{ renderer: "canvas" }} />
                  ) : (
                    <p className="py-12 text-center text-sm text-slate-400">暂无回撤数据</p>
                  )}
                </section>
              </div>
            )}

            {tab === "groups" && (
              <section className={chartCardClass()}>
                <h2 className="mb-2 text-lg font-bold tracking-tight text-slate-900">分组累计收益</h2>
                {groupCumOpt ? (
                  <ReactECharts option={groupCumOpt} style={{ height: 420 }} notMerge opts={{ renderer: "canvas" }} />
                ) : (
                  <p className="py-20 text-center text-sm text-slate-400">暂无分组累计序列</p>
                )}
              </section>
            )}

            {tab === "ic" && <ICDetectPanel fa={result?.factor_analysis} />}

            {tab === "industry" && (
              <IndustryDetectPanel fa={result?.factor_analysis} groups={groups} />
            )}

            {tab === "overview" && (
              <div className="space-y-5">
                {m && (
                  <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {[
                      ["Sharpe", num(m.sharpe)],
                      ["年化", pct(m.annual_return)],
                      ["最大回撤", pct(m.max_drawdown)],
                      ["Rank IC", num(m.rank_ic ?? result?.factor_analysis?.rank_ic_mean ?? m.ic)],
                      ["胜率", pct(m.win_rate)],
                      ["超额", pct(result?.excess_return)],
                    ].map(([k, v]) => (
                      <div key={k} className="rounded-xl border border-slate-200/90 bg-white p-4 shadow-sm">
                        <p className="text-xs text-slate-500">{k}</p>
                        <p className="mt-1 text-lg font-bold tabular-nums text-slate-900">{v}</p>
                      </div>
                    ))}
                  </section>
                )}

                <div className="grid gap-5 lg:grid-cols-2">
                  <section className={chartCardClass()}>
                    <h2 className="mb-2 text-sm font-semibold text-slate-800">分年收益</h2>
                    {annualOpt ? (
                      <ReactECharts option={annualOpt} style={{ height: 280 }} notMerge opts={{ renderer: "canvas" }} />
                    ) : (
                      <p className="py-16 text-center text-sm text-slate-400">暂无分年收益</p>
                    )}
                  </section>
                  <section className={chartCardClass()}>
                    <h2 className="mb-2 text-sm font-semibold text-slate-800">
                      分层区间收益
                      {typeof spread === "number" && (
                        <span className="ml-2 text-xs font-normal text-slate-400">spread {pct(spread)}</span>
                      )}
                    </h2>
                    {layerOpt ? (
                      <ReactECharts option={layerOpt} style={{ height: 280 }} notMerge opts={{ renderer: "canvas" }} />
                    ) : (
                      <p className="py-16 text-center text-sm text-slate-400">暂无分层汇总</p>
                    )}
                  </section>
                </div>

                {dds.length > 0 && (
                  <section className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
                    <div className="border-b border-slate-100 px-4 py-3">
                      <h2 className="text-sm font-semibold text-slate-800">回撤区间标注</h2>
                      <p className="mt-0.5 text-[11px] text-slate-400">
                        每一行是一次从高点回落到谷底的过程。「回到前高」为净值再次涨回该次回撤起点峰值的日期；若显示「尚未修复」，表示到回测结束仍未回到前高。
                      </p>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-sm">
                        <thead className="bg-slate-50 text-xs text-slate-500">
                          <tr>
                            <th className="px-4 py-2">开始</th>
                            <th className="px-4 py-2">谷底</th>
                            <th className="px-4 py-2">深度</th>
                            <th className="px-4 py-2">天数</th>
                            <th className="px-4 py-2">回到前高</th>
                          </tr>
                        </thead>
                        <tbody>
                          {dds.map((d, i) => (
                            <tr key={i} className="border-t border-slate-100">
                              <td className="px-4 py-2 font-mono text-xs">{d.start}</td>
                              <td className="px-4 py-2 font-mono text-xs">{d.end}</td>
                              <td className="px-4 py-2 tabular-nums text-red-600">{pct(d.depth)}</td>
                              <td className="px-4 py-2 tabular-nums">{d.days ?? "—"}</td>
                              <td className="px-4 py-2 font-mono text-xs">{d.recovery ?? "尚未修复"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                )}
              </div>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}

function MetaChip({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-slate-100 bg-slate-50/80 px-2.5 py-1.5">
      {icon}
      <div className="min-w-0">
        <p className="text-[10px] text-slate-400">{label}</p>
        <p className="truncate text-xs font-semibold text-slate-800">{value}</p>
      </div>
    </div>
  );
}
