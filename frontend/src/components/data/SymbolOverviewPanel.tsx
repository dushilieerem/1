import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Maximize2 } from "lucide-react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import {
  changeToneClass,
  clearMarketDailyCache,
  clearPersistedDailyCache,
  computeOverviewStats,
  fetchMarketDaily,
  fmtPct,
  fmtPrice,
  mergeMarketDaily,
  peekPersistedDaily,
  yearlyRangesBack,
  type MarketDaily,
} from "@/lib/marketDataApi";
import { streamMarketHistory } from "@/lib/marketHistory";
import {
  PERIOD_TABS,
  aggregateBars,
  formatThsCrosshairDate,
  type PeriodKey,
} from "@/lib/chartPeriods";

/** 日历日往前推 lookback 天 → YYYY-MM-DD */
function recentDailyStart(lookbackDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() - lookbackDays);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function withTimeout<T>(p: Promise<T>, ms: number, label: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = window.setTimeout(() => {
      reject(new Error(`${label}超时（>${ms / 1000}s）`));
    }, ms);
    p.then(
      (v) => {
        window.clearTimeout(t);
        resolve(v);
      },
      (e) => {
        window.clearTimeout(t);
        reject(e);
      },
    );
  });
}

export function SymbolOverviewPanel({
  symbol,
  chartFrom,
}: {
  symbol: string;
  chartFrom?: string;
}) {
  const code = symbol.trim();
  const [params] = useSearchParams();
  const fresh = params.get("fresh") === "1";
  const seeded = !fresh ? peekPersistedDaily(code) : null;
  const [daily, setDaily] = useState<MarketDaily | null>(seeded);
  const [err, setErr] = useState<string | null>(null);
  /** 尚无任何日线（有本地缓存则不必挡首屏） */
  const [awaitingFirst, setAwaitingFirst] = useState(!seeded?.bars?.length);
  /** 已有近端图，正在补更长历史 */
  const [enriching, setEnriching] = useState(Boolean(seeded?.bars?.length));
  const [period, setPeriod] = useState<PeriodKey>("day");
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartApi = useRef<IChartApi | null>(null);
  const seriesApi = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const barCountRef = useRef(0);
  const dailyBarsRef = useRef(seeded?.bars?.length || 0);
  const lineBarsRef = useRef<
    { date: string; open: number; high: number; low: number; close: number }[]
  >([]);

  useEffect(() => {
    if (!code) return;
    let cancelled = false;
    setErr(null);

    if (fresh) {
      clearMarketDailyCache();
      clearPersistedDailyCache(code);
      setDaily(null);
      dailyBarsRef.current = 0;
      setAwaitingFirst(true);
      setEnriching(false);
    } else {
      const hit = peekPersistedDaily(code);
      if (hit?.bars?.length) {
        setDaily(hit);
        dailyBarsRef.current = hit.bars.length;
        setAwaitingFirst(false);
        setEnriching(true);
      } else {
        setDaily(null);
        dailyBarsRef.current = 0;
        setAwaitingFirst(true);
        setEnriching(false);
      }
    }
    const bypass = fresh;

    let loadedDaily = fresh ? null : peekPersistedDaily(code);
    const applyMerged = (chunk: MarketDaily | null | undefined) => {
      if (!chunk?.bars?.length) return false;
      // 在请求流程内累积，再提交状态；避免 React 重放 updater 时被可变 ref 丢弃新数据。
      loadedDaily = mergeMarketDaily(loadedDaily, chunk);
      dailyBarsRef.current = loadedDaily?.bars.length || 0;
      setDaily(loadedDaily);
      return true;
    };

    void (async () => {
      const yieldPaint = () =>
        new Promise<void>((r) => {
          requestAnimationFrame(() => setTimeout(r, 0));
        });

      const pull = (start?: string, end?: string, ms = 15_000, label = "日线") =>
        withTimeout(
          fetchMarketDaily(code, { start, end, bypassCache: bypass }),
          ms,
          label,
        ).catch(() => null);

      // 1) 近端先画（约半年）
      const near = await pull(recentDailyStart(180), undefined, 15_000, "近端日线");
      if (cancelled) return;
      if (near?.bars?.length) {
        applyMerged(near);
        setAwaitingFirst(false);
        setEnriching(true);
        setErr(null);
        await yieldPaint();
      }

      // 2) 按自然年从近往远补齐至库底；近年或中间空年都不能截断历史。
      const years = yearlyRangesBack({ earliestYear: 2005 });
      for await (const chunk of streamMarketHistory(
        years,
        ({ start, end }) => pull(start, end, 20_000, `日线 ${start.slice(0, 4)}`),
        () => cancelled,
      )) {
        applyMerged(chunk);
        setAwaitingFirst(false);
        setEnriching(true);
        setErr(null);
        await yieldPaint();
      }

      if (!cancelled) {
        if (dailyBarsRef.current === 0) {
          // 空结果（含退市/早于库底）：不是超时失败，勿写「请稍后重试」
          setErr("暂无日线数据");
        }
        setEnriching(false);
        setAwaitingFirst(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [code, fresh]);

  const stats = useMemo(
    () => (daily ? computeOverviewStats(daily) : null),
    [daily],
  );
  const lineBars = useMemo(
    () => (daily ? aggregateBars(daily.bars || [], period) : []),
    [daily, period],
  );
  lineBarsRef.current = lineBars;

  const paintBars = (bars: typeof lineBars) => {
    if (!seriesApi.current || !chartApi.current) return;
    if (!bars.length) {
      seriesApi.current.setData([]);
      barCountRef.current = 0;
      return;
    }
    const data = bars.map((b) => ({
      time: b.date as Time,
      open: Number(b.open),
      high: Number(b.high),
      low: Number(b.low),
      close: Number(b.close),
    }));
    barCountRef.current = data.length;
    seriesApi.current.setData(data);
    chartApi.current.timeScale().fitContent();
  };

  // 框架一挂上就建空图；建好后立刻刷当前已有 bars（避免数据先到、图后挂的空窗）
  useEffect(() => {
    const el = chartRef.current;
    if (!el) return;

    chartApi.current?.remove();
    chartApi.current = null;
    seriesApi.current = null;

    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#94a3b8",
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "#e2e8f0" },
        horzLines: { color: "#e2e8f0" },
      },
      localization: {
        locale: "zh-CN",
        dateFormat: "yyyy-MM-dd",
        timeFormatter: formatThsCrosshairDate,
      },
      rightPriceScale: {
        borderVisible: false,
        scaleMargins: { top: 0.08, bottom: 0.08 },
        // 无数据时也画出空坐标骨架，避免整块白屏
        visible: true,
      },
      timeScale: {
        borderVisible: false,
        rightOffset: 2,
        fixLeftEdge: false,
        fixRightEdge: false,
        minBarSpacing: 0.05,
        // 先铺一段可见时间轴，数据到了再 fitContent
        ticksVisible: true,
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: "#94a3b8",
          style: LineStyle.Dashed,
          labelBackgroundColor: "#0f172a",
        },
        horzLine: {
          color: "#94a3b8",
          style: LineStyle.Dashed,
          labelBackgroundColor: "#0f172a",
        },
      },
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#e11d48",
      downColor: "#059669",
      borderUpColor: "#e11d48",
      borderDownColor: "#059669",
      wickUpColor: "#e11d48",
      wickDownColor: "#059669",
      lastValueVisible: true,
      priceLineVisible: true,
    });
    chartApi.current = chart;
    seriesApi.current = series;

    // 空图即可，不要画假 K（超时后会看起来像「坏图」）
    if (lineBarsRef.current.length) {
      paintBars(lineBarsRef.current);
    }

    let clampingRange = false;
    chart.timeScale().subscribeVisibleLogicalRangeChange((vr) => {
      if (!vr || clampingRange) return;
      const n = barCountRef.current;
      if (n < 2) return;
      const span = Number(vr.to) - Number(vr.from);
      if (!(span > 0)) return;
      const pad = span / 3;
      const minFrom = -pad;
      const maxTo = n - 1 + pad;
      let from = Number(vr.from);
      let to = Number(vr.to);
      let changed = false;
      if (from < minFrom) {
        from = minFrom;
        to = from + span;
        changed = true;
      }
      if (to > maxTo) {
        to = maxTo;
        from = to - span;
        if (from < minFrom) {
          from = minFrom;
          to = Math.min(maxTo, from + span);
        }
        changed = true;
      }
      if (!changed) return;
      if (Math.abs(from - Number(vr.from)) < 1e-6 && Math.abs(to - Number(vr.to)) < 1e-6) return;
      clampingRange = true;
      try {
        chart.timeScale().setVisibleLogicalRange({ from, to });
      } catch {
        /* ignore */
      } finally {
        clampingRange = false;
      }
    });

    return () => {
      chart.remove();
      chartApi.current = null;
      seriesApi.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅随标的重建；bars 由下一 effect 刷
  }, [code]);

  useEffect(() => {
    if (!seriesApi.current) return;
    if (!lineBars.length) return;
    // 真数据到达：恢复红绿配色并替换骨架
    seriesApi.current.applyOptions({
      upColor: "#e11d48",
      downColor: "#059669",
      borderUpColor: "#e11d48",
      borderDownColor: "#059669",
      wickUpColor: "#e11d48",
      wickDownColor: "#059669",
      lastValueVisible: true,
      priceLineVisible: true,
    });
    paintBars(lineBars);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lineBars]);

  const tone = changeToneClass(stats?.changePct);
  const nameShow = (daily?.name || "").trim() || code;
  const symShow = daily?.symbol || code;

  const chartPath = `/data/symbol/${encodeURIComponent(code)}/chart`;
  const chartQuery = (() => {
    const q = new URLSearchParams();
    if (chartFrom) q.set("from", chartFrom);
    return q.toString() ? `?${q.toString()}` : "";
  })();
  const chartFsQuery = (() => {
    const q = new URLSearchParams();
    if (chartFrom) q.set("from", chartFrom);
    q.set("fs", "1");
    return `?${q.toString()}`;
  })();

  const statusHint = err
    ? err
    : awaitingFirst
      ? "加载近端日线…"
      : enriching
        ? "补全历史中…"
        : null;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
      <div className="space-y-5">
        <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm sm:p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between sm:gap-4">
            <div className="min-w-0">
              <h2 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
                {nameShow}
              </h2>
              <p className="mt-1 text-sm font-medium text-slate-500">{symShow}</p>
              <p className="mt-1.5 text-sm text-slate-400">
                {stats?.rangeStart || "—"} ~ {stats?.rangeEnd || "—"}
                {statusHint ? (
                  <span
                    className={`ml-2 ${
                      err
                        ? err.includes("暂无")
                          ? "text-slate-400"
                          : "text-red-500"
                        : "text-slate-300"
                    }`}
                  >
                    · {statusHint}
                  </span>
                ) : null}
              </p>
            </div>
            <Link
              to={`${chartPath}${chartQuery}`}
              className="inline-flex w-full shrink-0 items-center justify-center rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800 sm:w-auto"
            >
              查看 K 线图
            </Link>
          </div>
          <div className="mt-4 flex flex-wrap items-end gap-2 sm:mt-5 sm:gap-3">
            <span
              className={`text-3xl font-bold tabular-nums sm:text-4xl ${
                stats ? tone : "text-slate-300"
              }`}
            >
              {stats ? fmtPrice(stats.last) : "—"}
            </span>
            <span
              className={`pb-0.5 text-base font-semibold tabular-nums sm:pb-1 sm:text-lg ${
                stats ? tone : "text-slate-300"
              }`}
            >
              {stats == null
                ? "—"
                : stats.change == null
                  ? "—"
                  : `${stats.change > 0 ? "+" : ""}${fmtPrice(stats.change)} ${fmtPct(stats.changePct)}`}
            </span>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200/80 bg-white p-3 shadow-sm sm:p-4">
          <div className="mb-3 flex items-center gap-2">
            <div className="flex min-w-0 flex-1 items-end gap-3 overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden sm:gap-5">
              {PERIOD_TABS.map((t) => {
                const on = period === t.key;
                return (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => setPeriod(t.key)}
                    className={`relative shrink-0 pb-1.5 text-sm transition-colors ${
                      on
                        ? "font-bold text-slate-900"
                        : "font-medium text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    {t.label}
                    {on ? (
                      <span className="absolute inset-x-0 bottom-0 mx-auto h-0.5 w-4 rounded-full bg-rose-500" />
                    ) : null}
                  </button>
                );
              })}
            </div>
            <Link
              to={`${chartPath}${chartFsQuery}`}
              title="横屏全屏"
              aria-label="横屏全屏"
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 lg:hidden"
            >
              <Maximize2 className="h-3.5 w-3.5" />
            </Link>
          </div>
          <div className="relative">
            <div
              ref={chartRef}
              className="h-[240px] w-full min-w-0 sm:h-[320px]"
            />
            {/* 不挡图：角落小条，像聚宽「先出框再填数」 */}
            {awaitingFirst || enriching ? (
              <div className="pointer-events-none absolute bottom-2 left-2 rounded-md bg-slate-900/75 px-2 py-1 text-[11px] font-medium text-white shadow">
                {awaitingFirst ? "加载近端…" : "补全历史…"}
              </div>
            ) : null}
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-800">区间表现</h3>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-6">
            {(["1D", "1W", "1M", "3M", "1Y", "YTD"] as const).map((k) => {
              const v = stats?.perf[k] ?? null;
              return (
                <div
                  key={k}
                  className="rounded-xl bg-slate-50 px-3 py-2.5 text-center"
                >
                  <p className="text-[11px] font-medium text-slate-400">{k}</p>
                  <p
                    className={`mt-1 text-sm font-semibold tabular-nums ${
                      v == null ? "text-slate-300" : changeToneClass(v)
                    }`}
                  >
                    {v == null ? "—" : fmtPct(v)}
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
                ["开盘", stats ? fmtPrice(stats.open) : "—"],
                ["最高", stats ? fmtPrice(stats.high) : "—"],
                ["最低", stats ? fmtPrice(stats.low) : "—"],
                ["收盘", stats ? fmtPrice(stats.last) : "—"],
                ["昨收", stats ? fmtPrice(stats.prevClose) : "—"],
                ["近一年高", stats ? fmtPrice(stats.high52) : "—"],
                ["近一年低", stats ? fmtPrice(stats.low52) : "—"],
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
