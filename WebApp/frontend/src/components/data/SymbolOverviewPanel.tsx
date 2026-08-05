import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  AreaSeries,
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import {
  changeToneClass,
  computeOverviewStats,
  fetchMarketDaily,
  fmtPct,
  fmtPrice,
  type MarketDaily,
} from "@/lib/marketDataApi";

type RangeKey = "1M" | "3M" | "1Y" | "YTD" | "ALL";

function ymdLocal(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function filterBars(daily: MarketDaily, key: RangeKey) {
  const bars = daily.bars || [];
  if (!bars.length || key === "ALL") return bars;
  const end = bars[bars.length - 1].date;
  const endDate = new Date(end + "T12:00:00");
  const start = new Date(endDate);
  if (key === "1M") start.setMonth(start.getMonth() - 1);
  else if (key === "3M") start.setMonth(start.getMonth() - 3);
  else if (key === "1Y") start.setFullYear(start.getFullYear() - 1);
  else if (key === "YTD") {
    return bars.filter((b) => b.date.startsWith(end.slice(0, 4)));
  }
  const s = ymdLocal(start);
  return bars.filter((b) => b.date >= s);
}

export function SymbolOverviewPanel({
  symbol,
  chartFrom,
}: {
  symbol: string;
  chartFrom?: string;
}) {
  const code = symbol.trim();
  const [daily, setDaily] = useState<MarketDaily | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [range, setRange] = useState<RangeKey>("1Y");
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartApi = useRef<IChartApi | null>(null);
  const seriesApi = useRef<ISeriesApi<"Area"> | null>(null);

  useEffect(() => {
    if (!code) return;
    let cancelled = false;
    setLoading(true);
    setErr(null);
    chartApi.current?.remove();
    chartApi.current = null;
    seriesApi.current = null;
    void fetchMarketDaily(code)
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
  }, [code]);

  const stats = useMemo(
    () => (daily ? computeOverviewStats(daily) : null),
    [daily],
  );
  const lineBars = useMemo(
    () => (daily ? filterBars(daily, range) : []),
    [daily, range],
  );

  useEffect(() => {
    if (loading || err || !daily || !chartRef.current) return;
    if (chartApi.current) return;
    const chart = createChart(chartRef.current, {
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
      rightPriceScale: {
        borderVisible: false,
        scaleMargins: { top: 0.12, bottom: 0.12 },
      },
      timeScale: {
        borderVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
        rightOffset: 4,
      },
      crosshair: { horzLine: { labelBackgroundColor: "#0f172a" } },
    });
    const series = chart.addSeries(AreaSeries, {
      lineColor: "#0ea5e9",
      topColor: "rgba(14, 165, 233, 0.28)",
      bottomColor: "rgba(14, 165, 233, 0.02)",
      lineWidth: 2,
      lastValueVisible: true,
      priceLineVisible: true,
    });
    chartApi.current = chart;
    seriesApi.current = series;
    return () => {
      chart.remove();
      chartApi.current = null;
      seriesApi.current = null;
    };
  }, [loading, err, daily, code]);

  useEffect(() => {
    if (!seriesApi.current || !chartApi.current) return;
    const data = lineBars.map((b) => ({
      time: b.date as Time,
      value: Number(b.close),
    }));
    seriesApi.current.setData(data);
    const ts = chartApi.current.timeScale();
    ts.fitContent();
    const pad = Math.max(2, Math.round(data.length * 0.02));
    try {
      const range = ts.getVisibleLogicalRange();
      if (range) {
        ts.setVisibleLogicalRange({
          from: range.from - pad,
          to: range.to + pad,
        });
      }
    } catch {
      /* ignore */
    }
  }, [lineBars]);

  const tone = changeToneClass(stats?.changePct);

  if (loading) {
    return <p className="py-16 text-center text-sm text-slate-400">加载日线…</p>;
  }
  if (err) {
    return (
      <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
        {err}
      </p>
    );
  }
  if (!daily || !stats) {
    return <p className="py-16 text-center text-sm text-slate-400">无数据</p>;
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
      <div className="space-y-5">
        <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-3xl font-bold tracking-tight text-slate-900">
                {(daily.name || "").trim() || code}
              </h2>
              <p className="mt-1 text-sm font-medium text-slate-500">
                {daily.symbol || code}
              </p>
              <p className="mt-1.5 text-sm text-slate-400">
                {stats.rangeStart || "—"} ~ {stats.rangeEnd || "—"}
              </p>
            </div>
            <Link
              to={`/data/symbol/${encodeURIComponent(code)}/chart${
                chartFrom ? `?from=${encodeURIComponent(chartFrom)}` : ""
              }`}
              className="rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800"
            >
              查看 K 线图
            </Link>
          </div>
          <div className="mt-5 flex flex-wrap items-end gap-3">
            <span className={`text-4xl font-bold tabular-nums ${tone}`}>
              {fmtPrice(stats.last)}
            </span>
            <span className={`pb-1 text-lg font-semibold tabular-nums ${tone}`}>
              {stats.change == null
                ? "—"
                : `${stats.change > 0 ? "+" : ""}${fmtPrice(stats.change)}`}{" "}
              {fmtPct(stats.changePct)}
            </span>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
          <div className="mb-3 flex flex-wrap gap-1.5">
            {(["1M", "3M", "1Y", "YTD", "ALL"] as RangeKey[]).map((k) => (
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
          <div ref={chartRef} className="h-[320px] w-full" />
        </div>

        <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-800">区间表现</h3>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-6">
            {(["1D", "1W", "1M", "3M", "1Y", "YTD"] as const).map((k) => {
              const v = stats.perf[k];
              return (
                <div
                  key={k}
                  className="rounded-xl bg-slate-50 px-3 py-2.5 text-center"
                >
                  <p className="text-[11px] font-medium text-slate-400">{k}</p>
                  <p
                    className={`mt-1 text-sm font-semibold tabular-nums ${changeToneClass(v)}`}
                  >
                    {fmtPct(v)}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <aside>
        <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-800">关键统计</h3>
          <dl className="mt-3 space-y-2.5 text-sm">
            {(
              [
                ["开盘", fmtPrice(stats.open)],
                ["最高", fmtPrice(stats.high)],
                ["最低", fmtPrice(stats.low)],
                ["收盘", fmtPrice(stats.last)],
                ["昨收", fmtPrice(stats.prevClose)],
                ["近一年高", fmtPrice(stats.high52)],
                ["近一年低", fmtPrice(stats.low52)],
              ] as const
            ).map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3">
                <dt className="text-slate-500">{k}</dt>
                <dd className="tabular-nums font-medium text-slate-900">{v}</dd>
              </div>
            ))}
          </dl>
        </div>
      </aside>
    </div>
  );
}
