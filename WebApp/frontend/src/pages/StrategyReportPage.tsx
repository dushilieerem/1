import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import {
  BarChart3,
  Clock,
  Layers,
  Share2,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import {
  CHART,
  areaGradient,
  axisCategory,
  axisValuePct,
  chartCardClass,
  darkTooltip,
  legendBase,
} from "@/components/chartTheme";
import { getStoredUser } from "@/lib/auth";
import { buildStrategyShareDraft } from "@/lib/communityShare";
import {
  STRATEGY_BENCHMARK_OPTIONS,
  STRATEGY_UNIVERSE_OPTIONS,
  getStrategyRun,
  optionLabel,
  type StrategyRunRecord,
} from "@/lib/strategyStore";

type ReportTab = "equity" | "overview";

const NAV: { id: ReportTab; label: string; icon: typeof TrendingDown }[] = [
  { id: "equity", label: "累计收益与回撤", icon: TrendingDown },
  { id: "overview", label: "绩效概览", icon: BarChart3 },
];

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

function resolveUniverse(rec: StrategyRunRecord | null | undefined): string {
  const req = rec?.request as Record<string, unknown> | undefined;
  const meta = (rec?.result as { meta?: Record<string, unknown> } | undefined)?.meta;
  const raw =
    (typeof req?.universe === "string" && req.universe) ||
    (typeof meta?.universe === "string" && meta.universe) ||
    "";
  return raw;
}

function resolveBenchmark(rec: StrategyRunRecord | null | undefined): string {
  const req = rec?.request as Record<string, unknown> | undefined;
  const meta = (rec?.result as { meta?: Record<string, unknown> } | undefined)?.meta;
  const raw =
    (typeof req?.benchmark === "string" && req.benchmark) ||
    (typeof meta?.benchmark === "string" && meta.benchmark) ||
    "";
  return raw;
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

function legendTopRight(data: string[]) {
  return {
    ...legendBase({ top: 4, right: 8, left: "auto" }),
    data,
  };
}

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

export function StrategyReportPage() {
  const { runId = "" } = useParams();
  const navigate = useNavigate();
  const [rec, setRec] = useState<StrategyRunRecord | null | undefined>(undefined);
  const [tab, setTab] = useState<ReportTab>("equity");

  useEffect(() => {
    let cancelled = false;
    setRec(undefined);
    void getStrategyRun(runId)
      .then((r) => {
        if (!cancelled) setRec(r);
      })
      .catch(() => {
        if (!cancelled) setRec(null);
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const result = rec?.result;
  const m = result?.metrics;
  const req = rec?.request;

  const curveDates = useMemo(
    () => result?.equity_curve?.map((p) => p.date) || [],
    [result],
  );
  const stratPct = useMemo(
    () => (result?.equity_curve || []).map((p) => toCumPct(p.value)),
    [result],
  );
  const benchPct = useMemo(() => {
    const c = result?.equity_curve;
    if (!c?.length) return [] as (number | null)[];
    const benchMap = new Map(
      (result?.benchmark_curve || []).map((p) => [p.date, p.value]),
    );
    return c.map((p) => {
      const bv = benchMap.get(p.date);
      return bv == null ? null : toCumPct(bv);
    });
  }, [result]);
  const hasBench = benchPct.some((v) => v != null);
  const ddPct = useMemo(
    () => (result?.equity_curve || []).map((p) => (p.drawdown ?? 0) * 100),
    [result],
  );

  const mddMeta = useMemo(() => {
    const curve = result?.equity_curve || [];
    const fromMetric = result?.metrics?.max_drawdown;
    const mddPct =
      typeof fromMetric === "number" && !Number.isNaN(fromMetric)
        ? fromMetric * 100
        : ddPct.length
          ? Math.min(...ddPct)
          : 0;
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

  const equityOpt = useMemo(() => {
    if (!curveDates.length) return null;
    return {
      color: [CHART.ink, CHART.bench],
      tooltip: {
        ...darkTooltip(),
        formatter: (
          params: Array<{
            seriesName: string;
            value: number | null;
            axisValue: string;
            marker: string;
          }>,
        ) => {
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

  const drawdownOpt = useMemo(() => {
    if (!curveDates.length) return null;
    return {
      color: [CHART.amber],
      tooltip: {
        ...darkTooltip(),
        formatter: (
          params: Array<{ value: number; axisValue: string; marker: string }>,
        ) => {
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

  const annualOpt = useMemo(() => {
    const rows = result?.annual_returns;
    if (!rows?.length) return null;
    const vals = rows.map((r) => (r.return_value ?? 0) * 100);
    return {
      tooltip: {
        ...darkTooltip(),
        trigger: "item",
        formatter: (p: {
          dataIndex: number;
          value: number | { value: number };
          marker: string;
        }) => {
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
            itemStyle: {
              color: v >= 0 ? CHART.positive : CHART.negative,
              borderRadius: [4, 4, 0, 0],
            },
          })),
        },
      ],
    };
  }, [result]);

  if (rec === undefined) {
    return (
      <div className="mx-auto max-w-lg px-6 py-20 text-center text-slate-400">
        加载中…
      </div>
    );
  }

  if (!rec) {
    return (
      <div className="mx-auto max-w-lg px-6 py-20 text-center">
        <p className="text-slate-600">没有找到回测结果。</p>
        <Link
          to="/strategy/research"
          className="mt-4 inline-block text-sm font-medium text-blue-600 underline"
        >
          返回策略研究
        </Link>
      </div>
    );
  }

  const dds = result?.drawdowns || [];
  const rangeLabel =
    req?.start && req?.end
      ? `${req.start} ~ ${req.end}`
      : result?.date_range?.start && result?.date_range?.end
        ? `${result.date_range.start} ~ ${result.date_range.end}`
        : "—";
  const uniCode = resolveUniverse(rec);
  const bmCode = resolveBenchmark(rec);

  const shareToCommunity = () => {
    const next = `/community/new?section=strategy`;
    if (!getStoredUser()) {
      navigate(`/login?next=${encodeURIComponent(next)}`);
      return;
    }
    const draft = buildStrategyShareDraft({
      name: rec.name || rec.description || "策略回测",
      rangeLabel,
      universeLabel: optionLabel(uniCode, STRATEGY_UNIVERSE_OPTIONS),
      benchmarkLabel: optionLabel(bmCode, STRATEGY_BENCHMARK_OPTIONS),
      metrics: m,
      excessReturn: result?.excess_return,
      strategyCode: req?.strategy_code,
    });
    navigate(next, { state: draft });
  };

  const candidates: Array<[string, string | null]> = [
    ["年化", m?.annual_return != null ? pct(m.annual_return) : null],
    ["夏普", m?.sharpe != null ? num(m.sharpe) : null],
    ["最大回撤", m?.max_drawdown != null ? pct(m.max_drawdown) : null],
    [
      "波动",
      m?.volatility != null || m?.annual_vol != null
        ? pct(m?.volatility ?? m?.annual_vol)
        : null,
    ],
    ["Calmar", m?.calmar != null ? num(m.calmar) : null],
    ["胜率", m?.win_rate != null ? pct(m.win_rate) : null],
    [
      "累计收益",
      m?.total_return != null || m?.cumulative_return != null
        ? pct(m?.total_return ?? m?.cumulative_return)
        : null,
    ],
    [
      "换手",
      m?.turnover != null || m?.avg_turnover != null
        ? num(m?.turnover ?? m?.avg_turnover)
        : null,
    ],
    ["超额", result?.excess_return != null ? pct(result.excess_return) : null],
  ];
  const metricCards: Array<[string, string]> = candidates.filter(
    (c): c is [string, string] => c[1] != null,
  );
  const shownCards: Array<[string, string]> =
    metricCards.length > 0
      ? metricCards
      : [
          ["年化", "—"],
          ["夏普", "—"],
          ["最大回撤", "—"],
          ["胜率", "—"],
        ];

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-gradient-to-b from-slate-50 to-white">
      <div className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-3 px-6 py-3">
          <div>
            <p className="text-sm text-slate-500">
              <Link to="/strategy/research" className="hover:text-blue-600">
                策略研究
              </Link>
              {" / "}
              <Link
                to={`/strategy/research/${rec.projectId}`}
                className="hover:text-blue-600"
              >
                {rec.name || rec.description}
              </Link>
              {" / 回测报告"}
            </p>
            <h1 className="mt-0.5 text-lg font-bold text-slate-900">
              {rec.name || rec.description}
            </h1>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={shareToCommunity}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              <Share2 className="h-3.5 w-3.5" />
              分享到社区
            </button>
            <Link
              to={`/strategy/research/${rec.projectId}/history`}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              历史记录
            </Link>
            <Link
              to={`/strategy/research/${rec.projectId}`}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              返回配置
            </Link>
          </div>
        </div>

        <div className="mx-auto grid max-w-[1400px] grid-cols-2 gap-2 px-6 pb-3 sm:grid-cols-3 lg:grid-cols-5">
          <MetaChip
            icon={<Clock className="h-3.5 w-3.5 text-blue-500" />}
            label="区间"
            value={rangeLabel}
          />
          <MetaChip
            icon={<Layers className="h-3.5 w-3.5 text-amber-500" />}
            label="股票池"
            value={optionLabel(uniCode, STRATEGY_UNIVERSE_OPTIONS)}
          />
          <MetaChip
            icon={<TrendingUp className="h-3.5 w-3.5 text-teal-500" />}
            label="基准"
            value={optionLabel(bmCode, STRATEGY_BENCHMARK_OPTIONS)}
          />
          <MetaChip
            icon={<BarChart3 className="h-3.5 w-3.5 text-slate-500" />}
            label="运行耗时"
            value={`${rec.elapsedSec}s`}
          />
          <MetaChip
            icon={<TrendingDown className="h-3.5 w-3.5 text-rose-500" />}
            label="起始资金"
            value={
              req?.initial_capital != null
                ? req.initial_capital.toLocaleString("zh-CN")
                : "—"
            }
          />
        </div>
      </div>

      <div className="mx-auto max-w-[1400px] px-6 py-5">
        <nav className="mb-4 flex gap-1 overflow-x-auto border-b border-slate-200 pb-2 lg:hidden">
          {NAV.map((item) => (
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
          <aside className="hidden w-44 shrink-0 lg:block">
            <nav className="sticky top-20 space-y-0.5">
              {NAV.map((item) => (
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
                  <h2 className="mb-2 text-lg font-bold tracking-tight text-slate-900">
                    累计收益
                  </h2>
                  {equityOpt ? (
                    <ReactECharts
                      option={equityOpt}
                      style={{ height: 320 }}
                      notMerge
                      opts={{ renderer: "canvas" }}
                    />
                  ) : (
                    <p className="py-16 text-center text-sm text-slate-400">
                      暂无净值数据
                    </p>
                  )}
                </section>

                <section className={chartCardClass()}>
                  <h2 className="mb-2 text-lg font-bold tracking-tight text-slate-900">
                    动态回撤
                  </h2>
                  {drawdownOpt ? (
                    <ReactECharts
                      option={drawdownOpt}
                      style={{ height: 240 }}
                      notMerge
                      opts={{ renderer: "canvas" }}
                    />
                  ) : (
                    <p className="py-12 text-center text-sm text-slate-400">
                      暂无回撤数据
                    </p>
                  )}
                </section>
              </div>
            )}

            {tab === "overview" && (
              <div className="space-y-5">
                <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {shownCards.map(([k, v]) => (
                    <div
                      key={k}
                      className="rounded-xl border border-slate-200/90 bg-white p-4 shadow-sm"
                    >
                      <p className="text-xs text-slate-500">{k}</p>
                      <p className="mt-1 text-lg font-bold tabular-nums text-slate-900">
                        {v}
                      </p>
                    </div>
                  ))}
                </section>

                <section className={chartCardClass()}>
                  <h2 className="mb-2 text-sm font-semibold text-slate-800">
                    分年收益
                  </h2>
                  {annualOpt ? (
                    <ReactECharts
                      option={annualOpt}
                      style={{ height: 280 }}
                      notMerge
                      opts={{ renderer: "canvas" }}
                    />
                  ) : (
                    <p className="py-16 text-center text-sm text-slate-400">
                      暂无分年收益
                    </p>
                  )}
                </section>

                {dds.length > 0 && (
                  <section className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
                    <div className="border-b border-slate-100 px-4 py-3">
                      <h2 className="text-sm font-semibold text-slate-800">
                        回撤区间
                      </h2>
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
                              <td className="px-4 py-2 font-mono text-xs">
                                {d.start}
                              </td>
                              <td className="px-4 py-2 font-mono text-xs">
                                {d.end}
                              </td>
                              <td className="px-4 py-2 tabular-nums text-red-600">
                                {pct(d.depth)}
                              </td>
                              <td className="px-4 py-2 tabular-nums">
                                {d.days ?? "—"}
                              </td>
                              <td className="px-4 py-2 font-mono text-xs">
                                {d.recovery ?? "尚未修复"}
                              </td>
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
