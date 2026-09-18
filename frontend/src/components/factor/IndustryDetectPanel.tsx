import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import {
  CHART,
  QUANTILE_PALETTE,
  SERIES_PALETTE,
  axisCategory,
  axisValuePct,
  chartCardClass,
  darkTooltip,
  legendBase,
} from "@/components/chartTheme";
import type { YgFactorAnalysis, YgIndustryEquityCurve, YgIndustryGroupEquityCurve } from "@/lib/ygApi";

type IndustryView = "equity" | "groups";

type Props = {
  fa: YgFactorAnalysis | null | undefined;
  groups?: number;
};

const TOP_N = 5;

function industryLabel(row: { industry_name?: string; industry_code?: string }, fallback: string) {
  return row.industry_name || row.industry_code || fallback;
}

function toCumPct(nav: number) {
  return (nav - 1) * 100;
}

function lastNav(curve: YgIndustryEquityCurve): number {
  const pts = curve.points || [];
  if (!pts.length) return Number.NEGATIVE_INFINITY;
  const v = pts[pts.length - 1]?.value;
  return typeof v === "number" && Number.isFinite(v) ? v : Number.NEGATIVE_INFINITY;
}

function lastGroupReturns(curves: YgIndustryGroupEquityCurve[], nGroups: number) {
  return curves
    .map((row, idx) => {
      const name = industryLabel(row, `行业${idx + 1}`);
      const pts = row.points || [];
      if (!pts.length) return null;
      const last = pts[pts.length - 1];
      const gmap = last.groups || {};
      const values: number[] = [];
      for (let i = 1; i <= nGroups; i++) {
        const v = gmap[`G${i}`] ?? gmap[`g${i}`] ?? gmap[`layer${i}`] ?? gmap[`Q${i}`];
        values.push(typeof v === "number" && Number.isFinite(v) ? toCumPct(v) : NaN);
      }
      if (values.every((v) => Number.isNaN(v))) return null;
      const score = values.filter((v) => Number.isFinite(v)).reduce((a, b) => Math.max(a, b), Number.NEGATIVE_INFINITY);
      return { name, values, score };
    })
    .filter((x): x is { name: string; values: number[]; score: number } => !!x);
}

function IndustryPicker({
  allNames,
  selected,
  onChange,
}: {
  allNames: string[];
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const selectedSet = useMemo(() => new Set(selected), [selected]);

  const toggle = (name: string) => {
    if (selectedSet.has(name)) onChange(selected.filter((x) => x !== name));
    else onChange([...selected, name]);
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50"
      >
        选择行业（已选 {selected.length}/{allNames.length}）
        <span className="ml-1 text-slate-400">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <>
          <button type="button" className="fixed inset-0 z-10 cursor-default" aria-label="关闭" onClick={() => setOpen(false)} />
          <div className="absolute left-0 z-20 mt-1 max-h-72 w-72 overflow-auto rounded-xl border border-slate-200 bg-white p-2 shadow-lg">
            <div className="mb-2 flex gap-2 border-b border-slate-100 pb-2">
              <button
                type="button"
                className="rounded px-2 py-0.5 text-[11px] text-teal-700 hover:bg-teal-50"
                onClick={() => onChange(allNames.slice(0, TOP_N))}
              >
                仅 Top{TOP_N}
              </button>
              <button
                type="button"
                className="rounded px-2 py-0.5 text-[11px] text-slate-600 hover:bg-slate-50"
                onClick={() => onChange([...allNames])}
              >
                全选
              </button>
              <button
                type="button"
                className="rounded px-2 py-0.5 text-[11px] text-slate-600 hover:bg-slate-50"
                onClick={() => onChange([])}
              >
                清空
              </button>
            </div>
            <ul className="space-y-0.5">
              {allNames.map((name) => {
                const on = selectedSet.has(name);
                return (
                  <li key={name}>
                    <label className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 text-xs hover:bg-slate-50">
                      <input type="checkbox" checked={on} onChange={() => toggle(name)} className="rounded border-slate-300" />
                      <span className={on ? "font-medium text-slate-800" : "text-slate-600"}>{name}</span>
                    </label>
                  </li>
                );
              })}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}

export function IndustryDetectPanel({ fa, groups = 5 }: Props) {
  const [view, setView] = useState<IndustryView>("equity");
  const nGroups = Math.min(Math.max(groups, 2), 10);

  const equityCurves = (fa?.industry_equity_curves || []) as YgIndustryEquityCurve[];
  const groupCurves = (fa?.industry_group_equity_curves || []) as YgIndustryGroupEquityCurve[];

  const rankedEquity = useMemo(() => {
    return [...equityCurves]
      .map((c, i) => ({ curve: c, name: industryLabel(c, `行业${i + 1}`), score: lastNav(c) }))
      .sort((a, b) => b.score - a.score);
  }, [equityCurves]);

  const barRowsAll = useMemo(() => {
    const rows = lastGroupReturns(groupCurves, nGroups);
    return [...rows].sort((a, b) => b.score - a.score);
  }, [groupCurves, nGroups]);

  const equityNames = useMemo(() => rankedEquity.map((r) => r.name), [rankedEquity]);
  const barNames = useMemo(() => barRowsAll.map((r) => r.name), [barRowsAll]);

  const [selectedEquity, setSelectedEquity] = useState<string[]>([]);
  const [selectedBars, setSelectedBars] = useState<string[]>([]);

  useEffect(() => {
    setSelectedEquity(equityNames.slice(0, TOP_N));
  }, [equityNames]);

  useEffect(() => {
    setSelectedBars(barNames.slice(0, TOP_N));
  }, [barNames]);

  const equityOpt = useMemo(() => {
    const show = new Set(selectedEquity);
    const picked = rankedEquity.filter((r) => show.has(r.name));
    if (!picked.length) return null;

    const allDates = new Set<string>();
    picked.forEach((r) => (r.curve.points || []).forEach((p) => allDates.add(p.date)));
    const dates = [...allDates].sort();
    const names = picked.map((r) => r.name);

    return {
      color: [...SERIES_PALETTE],
      tooltip: {
        ...darkTooltip(),
        formatter: (params: Array<{ seriesName: string; value: number | null; axisValue: string; marker: string }>) => {
          const head = params[0]?.axisValue ?? "";
          const rows = params
            .filter((p) => p.value != null && !Number.isNaN(Number(p.value)))
            .sort((a, b) => Number(b.value) - Number(a.value))
            .map((p) => `${p.marker} ${p.seriesName}: ${Number(p.value).toFixed(2)}%`)
            .join("<br/>");
          return `<b>${head}</b><br/>${rows || "—"}`;
        },
      },
      legend: { ...legendBase({ type: "scroll", top: 0, left: 0, right: 0 }), data: names },
      grid: { left: 56, right: 20, top: 48, bottom: 56 },
      xAxis: axisCategory({ data: dates }),
      yAxis: axisValuePct({ scale: true }),
      dataZoom: [
        { type: "inside" as const },
        {
          type: "slider" as const,
          height: 18,
          bottom: 8,
          borderColor: CHART.grid,
          fillerColor: "rgba(13,148,136,0.12)",
          handleStyle: { color: CHART.ink },
        },
      ],
      series: picked.map((r, i) => {
        const byDate = new Map((r.curve.points || []).map((p) => [p.date, p.value]));
        const color = SERIES_PALETTE[i % SERIES_PALETTE.length];
        return {
          name: r.name,
          type: "line" as const,
          smooth: 0.2,
          symbol: "none",
          lineStyle: { width: 2.2, color },
          itemStyle: { color },
          data: dates.map((d) => {
            const v = byDate.get(d);
            return v == null || !Number.isFinite(v) ? null : toCumPct(v);
          }),
        };
      }),
    };
  }, [rankedEquity, selectedEquity]);

  const barOpt = useMemo(() => {
    const show = new Set(selectedBars);
    const rows = barRowsAll.filter((r) => show.has(r.name));
    if (!rows.length) return null;
    const industries = rows.map((r) => r.name);
    const qLabels = Array.from({ length: nGroups }, (_, i) => `Q${i + 1}`);
    return {
      color: [...QUANTILE_PALETTE],
      tooltip: darkTooltip(),
      legend: { ...legendBase({ top: 0 }), data: qLabels },
      grid: { left: 56, right: 16, top: 40, bottom: 72 },
      dataZoom: [
        { type: "inside" as const },
        {
          type: "slider" as const,
          height: 18,
          bottom: 8,
          borderColor: CHART.grid,
          fillerColor: "rgba(13,148,136,0.12)",
          handleStyle: { color: CHART.ink },
        },
      ],
      xAxis: {
        type: "category" as const,
        data: industries,
        axisLabel: { rotate: 30, fontSize: 11, interval: 0, color: CHART.axis },
        axisLine: { lineStyle: { color: CHART.grid } },
        axisTick: { show: false },
      },
      yAxis: axisValuePct({ scale: true }),
      series: qLabels.map((label, qi) => ({
        name: label,
        type: "bar" as const,
        barGap: "8%",
        barMaxWidth: 22,
        data: rows.map((r) => {
          const v = r.values[qi];
          return Number.isFinite(v) ? v : null;
        }),
        itemStyle: {
          color: QUANTILE_PALETTE[qi % QUANTILE_PALETTE.length],
          borderRadius: [3, 3, 0, 0],
        },
      })),
    };
  }, [barRowsAll, selectedBars, nGroups]);

  const hasAny = equityCurves.length > 0 || groupCurves.length > 0;

  if (!hasAny) {
    return (
      <div className="flex h-80 items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-500">
        暂无行业分析数据（请重新跑检测；或 RE 端行业映射为空）
      </div>
    );
  }

  const tabs: { id: IndustryView; label: string }[] = [
    { id: "equity", label: "各行业累计收益" },
    { id: "groups", label: "行业分组收益" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setView(t.id)}
            className={`rounded-full px-3.5 py-1.5 text-xs font-medium transition ${
              view === t.id ? "bg-teal-600 text-white shadow-sm" : "bg-teal-50 text-slate-600 hover:bg-teal-100"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {view === "equity" && (
        <section className={chartCardClass()}>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-bold tracking-tight text-slate-900">各行业累计收益</h2>
            <IndustryPicker allNames={equityNames} selected={selectedEquity} onChange={setSelectedEquity} />
          </div>
          {equityOpt ? (
            <ReactECharts option={equityOpt} style={{ height: 440 }} notMerge lazyUpdate opts={{ renderer: "canvas" }} />
          ) : (
            <p className="py-20 text-center text-sm text-slate-400">请至少选择一个行业</p>
          )}
        </section>
      )}

      {view === "groups" && (
        <section className={chartCardClass()}>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-bold tracking-tight text-slate-900">行业分组收益</h2>
            <IndustryPicker allNames={barNames} selected={selectedBars} onChange={setSelectedBars} />
          </div>
          {barOpt ? (
            <ReactECharts option={barOpt} style={{ height: 440 }} notMerge lazyUpdate opts={{ renderer: "canvas" }} />
          ) : (
            <p className="py-20 text-center text-sm text-slate-400">请至少选择一个行业</p>
          )}
        </section>
      )}
    </div>
  );
}
