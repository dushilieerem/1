import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import { fetchMarketDaily, type MarketBar, type MarketDaily } from "@/lib/marketDataApi";

type RangeKey = "1M" | "3M" | "1Y" | "5Y" | "ALL";

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

export function DataSymbolChartPage() {
  const { code = "" } = useParams();
  const symbol = decodeURIComponent(code).trim();
  const [daily, setDaily] = useState<MarketDaily | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [range, setRange] = useState<RangeKey>("1Y");
  const [hover, setHover] = useState<MarketBar | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const chartApi = useRef<IChartApi | null>(null);
  const seriesApi = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const barsRef = useRef<MarketBar[]>([]);

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
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#e11d48",
      downColor: "#059669",
      borderUpColor: "#e11d48",
      borderDownColor: "#059669",
      wickUpColor: "#e11d48",
      wickDownColor: "#059669",
    });
    chartApi.current = chart;
    seriesApi.current = series;

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
      seriesApi.current = null;
    };
  }, [loading, err]);

  useEffect(() => {
    if (!seriesApi.current || !daily) return;
    const bars = filterBars(daily.bars || [], range);
    barsRef.current = bars;
    seriesApi.current.setData(
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

  const up =
    hover != null ? Number(hover.close) >= Number(hover.open) : null;

  return (
    <div className="mx-auto flex max-w-[1440px] flex-col px-4 py-4 sm:px-6 lg:px-8">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Link
            to={`/data/symbol/${encodeURIComponent(symbol)}`}
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
        <div
          ref={wrapRef}
          className="h-[min(70vh,720px)] w-full overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm"
        />
      )}
    </div>
  );
}
