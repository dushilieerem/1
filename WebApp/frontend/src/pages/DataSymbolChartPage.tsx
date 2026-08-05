import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import { fetchMarketDaily, type MarketBar, type MarketDaily } from "@/lib/marketDataApi";
import {
  MA_DEFS,
  bollinger,
  filterHistByDates,
  filterLineByDates,
  macd,
  rsi,
  smaSeries,
  type LinePoint,
  type MaKey,
} from "@/lib/chartIndicators";

type RangeKey = "1M" | "3M" | "1Y" | "5Y" | "ALL";
type SubPane = "none" | "macd" | "rsi";

function ymdLocal(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function filterBars(bars: MarketBar[], key: RangeKey): MarketBar[] {
  if (!bars.length || key === "ALL") return bars;
  const end = bars[bars.length - 1].date;
  const endDate = new Date(end + "T12:00:00");
  const start = new Date(endDate);
  if (key === "1M") start.setMonth(start.getMonth() - 1);
  else if (key === "3M") start.setMonth(start.getMonth() - 3);
  else if (key === "1Y") start.setFullYear(start.getFullYear() - 1);
  else if (key === "5Y") start.setFullYear(start.getFullYear() - 5);
  const s = ymdLocal(start);
  return bars.filter((b) => b.date >= s);
}

function toLineData(points: LinePoint[]) {
  return points.map((p) => ({ time: p.time as Time, value: p.value }));
}

function valueAt(points: LinePoint[], date: string): number | null {
  for (let i = points.length - 1; i >= 0; i--) {
    if (points[i].time === date) return points[i].value;
  }
  return null;
}

const defaultMaOn = Object.fromEntries(
  MA_DEFS.map((d) => [d.key, d.defaultOn]),
) as Record<MaKey, boolean>;

export function DataSymbolChartPage() {
  const { code = "" } = useParams();
  const [params] = useSearchParams();
  const symbol = decodeURIComponent(code).trim();
  const fromWatchlist = params.get("from") === "watchlist";
  const [daily, setDaily] = useState<MarketDaily | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [range, setRange] = useState<RangeKey>("1Y");
  const [hover, setHover] = useState<MarketBar | null>(null);
  const [maOn, setMaOn] = useState<Record<MaKey, boolean>>(defaultMaOn);
  const [bollOn, setBollOn] = useState(false);
  const [subPane, setSubPane] = useState<SubPane>("none");

  const wrapRef = useRef<HTMLDivElement | null>(null);
  const chartApi = useRef<IChartApi | null>(null);
  const candleApi = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const maSeriesRef = useRef<Partial<Record<MaKey, ISeriesApi<"Line">>>>({});
  const bollRef = useRef<{
    mid?: ISeriesApi<"Line">;
    upper?: ISeriesApi<"Line">;
    lower?: ISeriesApi<"Line">;
  }>({});
  const subRef = useRef<{
    hist?: ISeriesApi<"Histogram">;
    dif?: ISeriesApi<"Line">;
    dea?: ISeriesApi<"Line">;
    rsi?: ISeriesApi<"Line">;
    lines: IPriceLine[];
  }>({ lines: [] });
  const barsRef = useRef<MarketBar[]>([]);
  const indCache = useRef<{
    ma: Partial<Record<MaKey, LinePoint[]>>;
    boll: ReturnType<typeof bollinger> | null;
    macd: ReturnType<typeof macd> | null;
    rsi: LinePoint[] | null;
  }>({ ma: {}, boll: null, macd: null, rsi: null });

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    setLoading(true);
    setErr(null);
    void fetchMarketDaily(symbol)
      .then((d) => {
        if (!cancelled) setDaily(d);
      })
      .catch((ex) => {
        if (!cancelled) {
          setDaily(null);
          setErr(ex instanceof Error ? ex.message : String(ex));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  // 全历史算指标，再按区间截取展示（短区间 MA60 仍有意义）
  useEffect(() => {
    if (!daily?.bars?.length) {
      indCache.current = { ma: {}, boll: null, macd: null, rsi: null };
      return;
    }
    const all = daily.bars;
    const ma: Partial<Record<MaKey, LinePoint[]>> = {};
    for (const d of MA_DEFS) {
      ma[d.key] = smaSeries(all, d.period);
    }
    indCache.current = {
      ma,
      boll: bollinger(all, 20, 2),
      macd: macd(all, 12, 26, 9),
      rsi: rsi(all, 14),
    };
  }, [daily]);

  useEffect(() => {
    if (loading || err || !wrapRef.current) return;
    if (chartApi.current) return;
    const chart = createChart(wrapRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#64748b",
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "#f1f5f9" },
        horzLines: { color: "#f1f5f9" },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
      crosshair: {
        mode: 1,
        vertLine: { color: "#94a3b8", labelBackgroundColor: "#0f172a" },
        horzLine: { color: "#94a3b8", labelBackgroundColor: "#0f172a" },
      },
    });
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: "#e11d48",
      downColor: "#059669",
      borderUpColor: "#e11d48",
      borderDownColor: "#059669",
      wickUpColor: "#e11d48",
      wickDownColor: "#059669",
    });
    chartApi.current = chart;
    candleApi.current = candle;

    for (const d of MA_DEFS) {
      maSeriesRef.current[d.key] = chart.addSeries(LineSeries, {
        color: d.color,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
    }
    bollRef.current.upper = chart.addSeries(LineSeries, {
      color: "rgba(100, 116, 139, 0.85)",
      lineWidth: 2,
      lineStyle: LineStyle.Dashed,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    bollRef.current.mid = chart.addSeries(LineSeries, {
      color: "rgba(168, 85, 247, 0.75)",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    bollRef.current.lower = chart.addSeries(LineSeries, {
      color: "rgba(100, 116, 139, 0.85)",
      lineWidth: 2,
      lineStyle: LineStyle.Dashed,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    chart.subscribeCrosshairMove((param) => {
      if (!param.time) {
        setHover(null);
        return;
      }
      const t = String(param.time);
      const bar = barsRef.current.find((b) => b.date === t) || null;
      setHover(bar);
    });

    return () => {
      chart.remove();
      chartApi.current = null;
      candleApi.current = null;
      maSeriesRef.current = {};
      bollRef.current = {};
      subRef.current = { lines: [] };
    };
  }, [loading, err]);

  // 副图切换时保留当前时间轴可视范围
  useEffect(() => {
    const chart = chartApi.current;
    if (!chart || loading || err) return;
    const kept = chart.timeScale().getVisibleLogicalRange();

    // 清掉旧副图 series（pane index > 0）
    const clearSub = () => {
      for (const pl of subRef.current.lines) {
        try {
          subRef.current.rsi?.removePriceLine(pl);
        } catch {
          /* ignore */
        }
      }
      subRef.current.lines = [];
      for (const key of ["hist", "dif", "dea", "rsi"] as const) {
        const s = subRef.current[key];
        if (s) {
          try {
            chart.removeSeries(s);
          } catch {
            /* ignore */
          }
          subRef.current[key] = undefined;
        }
      }
      try {
        const panes = chart.panes();
        for (let i = panes.length - 1; i >= 1; i--) {
          chart.removePane(i);
        }
      } catch {
        /* ignore */
      }
    };

    clearSub();
    if (subPane === "none") {
      if (kept) {
        try {
          chart.timeScale().setVisibleLogicalRange(kept);
        } catch {
          /* ignore */
        }
      }
      return;
    }

    const pane = chart.addPane(true);
    pane.setStretchFactor(0.35);

    if (subPane === "macd") {
      subRef.current.hist = pane.addSeries(HistogramSeries, {
        priceLineVisible: false,
        lastValueVisible: false,
      });
      subRef.current.dif = pane.addSeries(LineSeries, {
        color: "#3b82f6",
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      subRef.current.dea = pane.addSeries(LineSeries, {
        color: "#f59e0b",
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
    } else if (subPane === "rsi") {
      subRef.current.rsi = pane.addSeries(LineSeries, {
        color: "#a855f7",
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      const s = subRef.current.rsi;
      subRef.current.lines = [
        s.createPriceLine({
          price: 70,
          color: "rgba(225, 29, 72, 0.45)",
          lineWidth: 2,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: "70",
        }),
        s.createPriceLine({
          price: 30,
          color: "rgba(5, 150, 105, 0.45)",
          lineWidth: 2,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: "30",
        }),
      ];
    }

    if (kept) {
      try {
        chart.timeScale().setVisibleLogicalRange(kept);
      } catch {
        /* ignore */
      }
    }
  }, [subPane, loading, err]);

  useEffect(() => {
    if (!candleApi.current || !daily) return;
    const bars = filterBars(daily.bars || [], range);
    barsRef.current = bars;

    candleApi.current.setData(
      bars.map((b) => ({
        time: b.date as Time,
        open: Number(b.open),
        high: Number(b.high),
        low: Number(b.low),
        close: Number(b.close),
      })),
    );
    chartApi.current?.timeScale().fitContent();
    setHover(bars.length ? bars[bars.length - 1] : null);
  }, [daily, range, loading, err]);

  // 只更新叠加线 / 副图数据，不 fitContent，避免放大后点指标被拉回全图
  useEffect(() => {
    if (!candleApi.current || !daily) return;
    const bars = barsRef.current.length
      ? barsRef.current
      : filterBars(daily.bars || [], range);
    const dateSet = new Set(bars.map((b) => b.date));
    const chart = chartApi.current;
    const kept = chart?.timeScale().getVisibleLogicalRange() ?? null;

    for (const d of MA_DEFS) {
      const series = maSeriesRef.current[d.key];
      if (!series) continue;
      if (!maOn[d.key]) {
        series.setData([]);
        continue;
      }
      const full = indCache.current.ma[d.key] || [];
      series.setData(toLineData(filterLineByDates(full, dateSet)));
    }

    const boll = indCache.current.boll;
    if (bollOn && boll) {
      bollRef.current.upper?.setData(toLineData(filterLineByDates(boll.upper, dateSet)));
      bollRef.current.mid?.setData(toLineData(filterLineByDates(boll.mid, dateSet)));
      bollRef.current.lower?.setData(toLineData(filterLineByDates(boll.lower, dateSet)));
    } else {
      bollRef.current.upper?.setData([]);
      bollRef.current.mid?.setData([]);
      bollRef.current.lower?.setData([]);
    }

    if (subPane === "macd" && indCache.current.macd) {
      const m = indCache.current.macd;
      subRef.current.hist?.setData(
        filterHistByDates(m.hist, dateSet).map((p) => ({
          time: p.time as Time,
          value: p.value,
          color: p.color,
        })),
      );
      subRef.current.dif?.setData(toLineData(filterLineByDates(m.dif, dateSet)));
      subRef.current.dea?.setData(toLineData(filterLineByDates(m.dea, dateSet)));
    } else if (subPane === "rsi" && indCache.current.rsi) {
      subRef.current.rsi?.setData(
        toLineData(filterLineByDates(indCache.current.rsi, dateSet)),
      );
    }

    if (kept) {
      try {
        chart?.timeScale().setVisibleLogicalRange(kept);
      } catch {
        /* ignore */
      }
    }
  }, [daily, range, loading, err, maOn, bollOn, subPane]);

  const hoverInd = useMemo(() => {
    if (!hover) return null;
    const date = hover.date;
    const dateSet = new Set(barsRef.current.map((b) => b.date));
    const items: { label: string; color: string; value: number }[] = [];
    for (const d of MA_DEFS) {
      if (!maOn[d.key]) continue;
      const v = valueAt(filterLineByDates(indCache.current.ma[d.key] || [], dateSet), date);
      if (v != null) items.push({ label: d.label, color: d.color, value: v });
    }
    if (bollOn && indCache.current.boll) {
      const u = valueAt(filterLineByDates(indCache.current.boll.upper, dateSet), date);
      const m = valueAt(filterLineByDates(indCache.current.boll.mid, dateSet), date);
      const l = valueAt(filterLineByDates(indCache.current.boll.lower, dateSet), date);
      if (u != null) items.push({ label: "BOLL上", color: "#64748b", value: u });
      if (m != null) items.push({ label: "BOLL中", color: "#a855f7", value: m });
      if (l != null) items.push({ label: "BOLL下", color: "#64748b", value: l });
    }
    return items;
  }, [hover, maOn, bollOn, range, daily]);

  const up = hover != null ? Number(hover.close) >= Number(hover.open) : null;

  const toggleMa = (key: MaKey) => {
    setMaOn((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div className="mx-auto flex max-w-[1440px] flex-col px-4 py-4 sm:px-6 lg:px-8">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Link
            to={`/data/symbol/${encodeURIComponent(symbol)}${
              fromWatchlist ? "?from=watchlist" : ""
            }`}
            className="text-slate-500 hover:text-slate-800"
          >
            ← 返回概览
          </Link>
          <span className="text-slate-300">|</span>
          <h1 className="text-lg font-bold text-slate-900">
            {(daily?.name || "").trim() || symbol}
            {(daily?.name || "").trim() ? (
              <span className="ml-2 text-sm font-medium text-slate-500">
                {daily?.symbol || symbol}
              </span>
            ) : null}
          </h1>
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
            日线
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {(["1M", "3M", "1Y", "5Y", "ALL"] as RangeKey[]).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setRange(k)}
              className={
                range === k
                  ? "rounded-lg bg-slate-900 px-2.5 py-1 text-xs font-semibold text-white"
                  : "rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-200"
              }
            >
              {k}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-[11px] font-medium text-slate-400">指标</span>
        {MA_DEFS.map((d) => (
          <button
            key={d.key}
            type="button"
            onClick={() => toggleMa(d.key)}
            className={`rounded-md px-2 py-0.5 text-[11px] font-medium tabular-nums ${
              maOn[d.key]
                ? "bg-slate-900/5 ring-1 ring-slate-200"
                : "bg-slate-50 text-slate-400"
            }`}
            style={maOn[d.key] ? { color: d.color } : undefined}
          >
            {d.label}
          </button>
        ))}
        <button
          type="button"
          onClick={() => setBollOn((v) => !v)}
          className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${
            bollOn
              ? "bg-violet-50 text-violet-700 ring-1 ring-violet-200"
              : "bg-slate-50 text-slate-400"
          }`}
        >
          BOLL
        </button>
        <span className="mx-1 h-3 w-px bg-slate-200" />
        <span className="text-[11px] text-slate-400">副图</span>
        {(
          [
            ["none", "无"],
            ["macd", "MACD"],
            ["rsi", "RSI"],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            type="button"
            onClick={() => setSubPane(k)}
            className={
              subPane === k
                ? "rounded-md bg-slate-900 px-2 py-0.5 text-[11px] font-semibold text-white"
                : "rounded-md bg-slate-50 px-2 py-0.5 text-[11px] font-medium text-slate-500 hover:bg-slate-100"
            }
          >
            {label}
          </button>
        ))}
      </div>

      {hover ? (
        <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs tabular-nums text-slate-600">
          <span>{hover.date}</span>
          <span>开 {Number(hover.open).toFixed(2)}</span>
          <span>高 {Number(hover.high).toFixed(2)}</span>
          <span>低 {Number(hover.low).toFixed(2)}</span>
          <span
            className={
              up ? "font-semibold text-red-600" : "font-semibold text-emerald-600"
            }
          >
            收 {Number(hover.close).toFixed(2)}
          </span>
          {hoverInd?.map((it) => (
            <span key={it.label} style={{ color: it.color }}>
              {it.label} {it.value.toFixed(2)}
            </span>
          ))}
        </div>
      ) : (
        <div className="mb-2 h-4" />
      )}

      {loading ? (
        <p className="py-24 text-center text-sm text-slate-400">加载日线…</p>
      ) : err ? (
        <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {err}
        </p>
      ) : (
        <>
          <div
            ref={wrapRef}
            className="h-[min(70vh,720px)] w-full overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm"
          />
        </>
      )}
    </div>
  );
}
