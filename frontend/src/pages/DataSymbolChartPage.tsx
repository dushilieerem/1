import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Download, ImageDown, Maximize2, Scan, X } from "lucide-react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import { fetchMarketDaily, mergeMarketDaily, peekPersistedDaily, yearlyRangesBack, type MarketBar, type MarketDaily } from "@/lib/marketDataApi";
import { streamMarketHistory } from "@/lib/marketHistory";
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
import {
  PERIOD_TABS,
  aggregateBars,
  formatThsCrosshairDate,
  type PeriodKey,
} from "@/lib/chartPeriods";

type SubPane = "none" | "macd" | "rsi" | "volume";

/** iPhone/iPad（含 iPadOS 桌面 UA） */
function isAppleTouchDevice() {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent || "";
  if (/iPhone|iPad|iPod/i.test(ua)) return true;
  return (
    navigator.platform === "MacIntel" && (navigator.maxTouchPoints || 0) > 1
  );
}

/** 可见视口（Safari 地址栏收起前后会变） */
function viewportSize() {
  const vv = window.visualViewport;
  return {
    w: Math.round(vv?.width ?? window.innerWidth),
    h: Math.round(vv?.height ?? window.innerHeight),
  };
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
  const fromParam = (params.get("from") || "").trim();
  const overviewQuery = fromParam
    ? fromParam.startsWith("news:")
      ? `?from=news&newsId=${encodeURIComponent(fromParam.slice(5))}`
      : fromParam === "news"
        ? "?from=news"
        : `?from=${encodeURIComponent(fromParam)}`
    : "";
  const seeded = peekPersistedDaily(symbol);
  const [daily, setDaily] = useState<MarketDaily | null>(seeded);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(!seeded?.bars?.length);
  const [period, setPeriod] = useState<PeriodKey>("day");
  const [hover, setHover] = useState<MarketBar | null>(null);
  const [maOn, setMaOn] = useState<Record<MaKey, boolean>>(defaultMaOn);
  const [bollOn, setBollOn] = useState(false);
  const [subPane, setSubPane] = useState<SubPane>("none");
  /** 仅手机：全屏。安卓竖屏可 CSS 伪横屏；苹果仅真横屏全屏（不 rotate，清晰） */
  const [fs, setFs] = useState(false);
  const [cssLandscape, setCssLandscape] = useState(false);
  /** 伪横屏舞台像素尺寸（安卓） */
  const [landBox, setLandBox] = useState({ w: 0, h: 0 });
  const [landSs, setLandSs] = useState(1);

  const wrapRef = useRef<HTMLDivElement | null>(null);
  const fsRootRef = useRef<HTMLDivElement | null>(null);
  const landSsRef = useRef(1);
  const fsRef = useRef(false);
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
    const hit = peekPersistedDaily(symbol);
    if (hit?.bars?.length) {
      setDaily(hit);
      setLoading(false);
    } else {
      setLoading(true);
    }
    setErr(null);
    void (async () => {
      const lookback = (days: number) => {
        const d = new Date();
        d.setDate(d.getDate() - days);
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      };
      try {
        const near = await fetchMarketDaily(symbol, {
          start: lookback(180),
        }).catch(() => null);
        if (cancelled) return;
        if (near?.bars?.length) {
          setDaily((prev) => mergeMarketDaily(prev, near) || prev);
          setLoading(false);
        }

        const years = yearlyRangesBack({ earliestYear: 2005 });
        for await (const chunk of streamMarketHistory(
          years,
          ({ start, end }) =>
            fetchMarketDaily(symbol, { start, end }).catch(() => null),
          () => cancelled,
        )) {
          setDaily((prev) => mergeMarketDaily(prev, chunk) || prev);
          setLoading(false);
        }

        if (cancelled) return;
        setDaily((prev) => {
          if (prev?.bars?.length) return prev;
          setErr("暂无日线数据");
          return prev;
        });
      } catch (ex) {
        if (!cancelled && !hit?.bars?.length) {
          setDaily(null);
          setErr(ex instanceof Error ? ex.message : String(ex));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  // 按当前周期聚合后再算指标（周 K 的 MA5 = 5 周）
  useEffect(() => {
    if (!daily?.bars?.length) {
      indCache.current = { ma: {}, boll: null, macd: null, rsi: null };
      return;
    }
    const all = aggregateBars(daily.bars, period);
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
  }, [daily, period]);

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
      localization: {
        locale: "zh-CN",
        dateFormat: "yyyy-MM-dd",
        timeFormatter: formatThsCrosshairDate,
      },
      rightPriceScale: { borderVisible: false },
      timeScale: {
        borderVisible: false,
        rightOffset: 0,
        // 左右均可空出约 1/3（见下方 range clamp）
        fixLeftEdge: false,
        fixRightEdge: false,
        // 默认 minBarSpacing≈0.5，窄屏无法缩到「全景」；放宽到可 fit 全历史
        minBarSpacing: 0.05,
      },
      // 与 PC 一致：左右拖时间轴、上下拖价格、双指缩放
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
      handleScale: {
        axisPressedMouseMove: true,
        axisDoubleClickReset: true,
        mouseWheel: true,
        pinch: true,
      },
      kineticScroll: {
        touch: true,
        mouse: false,
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

    // 左/右缘最多各空出可视宽度的约 1/3
    let clampingRange = false;
    chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (!range || clampingRange) return;
      const n = barsRef.current.length;
      if (n < 2) return;
      const span = Number(range.to) - Number(range.from);
      if (!(span > 0)) return;
      const pad = span / 3;
      const minFrom = -pad;
      const maxTo = n - 1 + pad;
      let from = Number(range.from);
      let to = Number(range.to);
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
      if (Math.abs(from - Number(range.from)) < 1e-6 && Math.abs(to - Number(range.to)) < 1e-6) return;
      clampingRange = true;
      try {
        chart.timeScale().setVisibleLogicalRange({ from, to });
      } catch {
        /* ignore */
      } finally {
        clampingRange = false;
      }
    });

    for (const d of MA_DEFS) {
      maSeriesRef.current[d.key] = chart.addSeries(LineSeries, {
        color: d.color,
        lineWidth: 1,
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

    if (subPane === "volume") {
      subRef.current.hist = pane.addSeries(HistogramSeries, {
        priceFormat: { type: "volume" },
        priceLineVisible: false,
        lastValueVisible: false,
      });
    } else if (subPane === "macd") {
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
    const bars = aggregateBars(daily.bars || [], period);
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
  }, [daily, period, loading, err]);

  // 只更新叠加线 / 副图数据，不 fitContent，避免放大后点指标被拉回全图
  useEffect(() => {
    if (!candleApi.current || !daily) return;
    const bars = barsRef.current.length
      ? barsRef.current
      : aggregateBars(daily.bars || [], period);
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
    } else if (subPane === "volume") {
      subRef.current.hist?.setData(
        bars
          .filter((b) => dateSet.has(b.date))
          .map((b) => ({
            time: b.date as Time,
            value: Number(b.volume || 0),
            color:
              Number(b.close) >= Number(b.open)
                ? "rgba(225, 29, 72, 0.55)"
                : "rgba(5, 150, 105, 0.55)",
          })),
      );
    }

    if (kept) {
      try {
        chart?.timeScale().setVisibleLogicalRange(kept);
      } catch {
        /* ignore */
      }
    }
  }, [daily, period, loading, err, maOn, bollOn, subPane]);

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
    if (subPane === "macd" && indCache.current.macd) {
      const m = indCache.current.macd;
      const dif = valueAt(filterLineByDates(m.dif, dateSet), date);
      const dea = valueAt(filterLineByDates(m.dea, dateSet), date);
      const hist = valueAt(filterLineByDates(m.hist, dateSet), date);
      if (dif != null) items.push({ label: "DIF", color: "#3b82f6", value: dif });
      if (dea != null) items.push({ label: "DEA", color: "#f59e0b", value: dea });
      if (hist != null) items.push({ label: "MACD", color: "#64748b", value: hist });
    }
    if (subPane === "rsi" && indCache.current.rsi) {
      const v = valueAt(filterLineByDates(indCache.current.rsi, dateSet), date);
      if (v != null) items.push({ label: "RSI", color: "#a855f7", value: v });
    }
    return items;
  }, [hover, maOn, bollOn, subPane, period, daily]);

  const up = hover != null ? Number(hover.close) >= Number(hover.open) : null;

  const toggleMa = (key: MaKey) => {
    setMaOn((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const syncCssLandscape = (active = fs) => {
    if (!active) {
      setCssLandscape(false);
      setLandBox({ w: 0, h: 0 });
      landSsRef.current = 1;
      setLandSs(1);
      return;
    }
    // 苹果：永不 CSS rotate
    if (isAppleTouchDevice()) {
      setCssLandscape(false);
      setLandBox({ w: 0, h: 0 });
      landSsRef.current = 1;
      setLandSs(1);
      return;
    }
    const portrait = window.matchMedia("(orientation: portrait)").matches;
    setCssLandscape(portrait);
    if (!portrait) {
      setLandBox({ w: 0, h: 0 });
      landSsRef.current = 1;
      setLandSs(1);
      return;
    }
    const { w: vw, h: vh } = viewportSize();
    landSsRef.current = 1;
    setLandSs(1);
    setLandBox({ w: vh, h: vw });
  };

  const exitFs = async () => {
    try {
      const ori = screen.orientation as ScreenOrientation & {
        unlock?: () => void;
      };
      ori.unlock?.();
    } catch {
      /* ignore */
    }
    const doc = document as Document & {
      webkitExitFullscreen?: () => Promise<void> | void;
    };
    if (
      document.fullscreenElement ||
      (doc as { webkitFullscreenElement?: Element }).webkitFullscreenElement
    ) {
      try {
        await (document.exitFullscreen?.() ?? doc.webkitExitFullscreen?.());
      } catch {
        /* ignore */
      }
    }
    fsRef.current = false;
    setFs(false);
    setCssLandscape(false);
    setLandBox({ w: 0, h: 0 });
    landSsRef.current = 1;
    setLandSs(1);
  };

  const enterFs = async () => {
    if (window.matchMedia("(min-width: 1024px)").matches) return;
    const apple = isAppleTouchDevice();
    const portrait = window.matchMedia("(orientation: portrait)").matches;

    // 苹果：仅真横屏进全屏（横持自动触发）；竖屏无操作
    if (apple && portrait) return;

    fsRef.current = true;
    setFs(true);
    if (apple) {
      setCssLandscape(false);
      setLandBox({ w: 0, h: 0 });
      landSsRef.current = 1;
      setLandSs(1);
    } else {
      setCssLandscape(portrait);
      if (portrait) {
        const { w: vw, h: vh } = viewportSize();
        landSsRef.current = 1;
        setLandSs(1);
        setLandBox({ w: vh, h: vw });
      }
    }
    requestAnimationFrame(() => {
      void (async () => {
        const el = fsRootRef.current as
          | (HTMLDivElement & {
              webkitRequestFullscreen?: () => Promise<void> | void;
            })
          | null;
        try {
          if (el && !document.fullscreenElement) {
            await (el.requestFullscreen?.() ?? el.webkitRequestFullscreen?.());
          }
        } catch {
          /* iOS 常拒绝，靠 fixed 遮罩 */
        }
        if (!apple) {
          try {
            const ori = screen.orientation as ScreenOrientation & {
              lock?: (o: string) => Promise<void>;
            };
            await ori.lock?.("landscape");
          } catch {
            /* 锁不住靠 CSS 伪横屏 */
          }
        }
        try {
          window.scrollTo(0, 1);
        } catch {
          /* ignore */
        }
        syncCssLandscape(true);
        window.dispatchEvent(new Event("resize"));
      })();
    });
  };

  // 苹果：横持 → 进全屏；竖回来 → 退出（无 CSS rotate，不糊）
  useEffect(() => {
    if (!isAppleTouchDevice()) return;
    if (loading || err) return;
    if (window.matchMedia("(min-width: 1024px)").matches) return;

    const onOrient = () => {
      if (window.matchMedia("(min-width: 1024px)").matches) return;
      const land = window.matchMedia("(orientation: landscape)").matches;
      if (land) {
        if (!fsRef.current) void enterFs();
      } else if (fsRef.current) {
        void exitFs();
      }
    };

    onOrient();
    window.addEventListener("orientationchange", onOrient);
    window.addEventListener("resize", onOrient);
    return () => {
      window.removeEventListener("orientationchange", onOrient);
      window.removeEventListener("resize", onOrient);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, err, symbol]);

  // ?fs=1：安卓直接进；苹果已横屏则进，竖屏等横持
  useEffect(() => {
    if (params.get("fs") !== "1") return;
    if (loading || err) return;
    if (window.matchMedia("(min-width: 1024px)").matches) return;
    if (isAppleTouchDevice()) {
      if (window.matchMedia("(orientation: landscape)").matches) void enterFs();
      return;
    }
    void enterFs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, err, symbol]);

  useEffect(() => {
    if (!fs) return;
    const prev = document.body.style.overflow;
    const prevHtml = document.documentElement.style.overflow;
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    syncCssLandscape(true);
    const sharpen = () => {
      window.dispatchEvent(new Event("resize"));
      try {
        const c = chartApi.current;
        const el = wrapRef.current;
        if (c && el) {
          const w = Math.max(1, Math.round(el.clientWidth));
          const h = Math.max(1, Math.round(el.clientHeight));
          c.resize(w, h, true);
        }
      } catch {
        /* ignore */
      }
    };
    const onOrient = () => {
      syncCssLandscape(true);
      requestAnimationFrame(sharpen);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") void exitFs();
    };
    window.addEventListener("orientationchange", onOrient);
    window.addEventListener("resize", onOrient);
    window.visualViewport?.addEventListener("resize", onOrient);
    window.visualViewport?.addEventListener("scroll", onOrient);
    window.addEventListener("keydown", onKey);
    const tmr = window.setTimeout(sharpen, 80);
    const tmr2 = window.setTimeout(sharpen, 320);
    return () => {
      document.body.style.overflow = prev;
      document.documentElement.style.overflow = prevHtml;
      window.removeEventListener("orientationchange", onOrient);
      window.removeEventListener("resize", onOrient);
      window.visualViewport?.removeEventListener("resize", onOrient);
      window.visualViewport?.removeEventListener("scroll", onOrient);
      window.removeEventListener("keydown", onKey);
      window.clearTimeout(tmr);
      window.clearTimeout(tmr2);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fs, cssLandscape]);

  // CSS 横屏：触摸轴与视觉对调
  useEffect(() => {
    if (!fs || !cssLandscape || loading || err) return;
    const el = wrapRef.current;
    const chart = chartApi.current;
    const candle = candleApi.current;
    if (!el || !chart || !candle) return;

    chart.applyOptions({
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: false,
        horzTouchDrag: false,
        vertTouchDrag: false,
      },
      handleScale: {
        axisPressedMouseMove: false,
        axisDoubleClickReset: true,
        mouseWheel: true,
        pinch: false,
      },
    });

    let lastX = 0;
    let lastY = 0;
    let dragging = false;
    let pinchDist = 0;

    const onStart = (e: TouchEvent) => {
      if (e.touches.length === 1) {
        dragging = true;
        lastX = e.touches[0].clientX;
        lastY = e.touches[0].clientY;
      } else if (e.touches.length === 2) {
        dragging = false;
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        pinchDist = Math.hypot(dx, dy);
      }
    };

    const onMove = (e: TouchEvent) => {
      e.preventDefault();
      if (e.touches.length === 1 && dragging) {
        const x = e.touches[0].clientX;
        const y = e.touches[0].clientY;
        const screenDx = x - lastX;
        const screenDy = y - lastY;
        lastX = x;
        lastY = y;
        const timePx = screenDy;
        const pricePx = -screenDx;

        const ts = chart.timeScale();
        const range = ts.getVisibleLogicalRange();
        if (range) {
          const ss = Math.max(1, landSsRef.current);
          const w = Math.max(1, el.clientWidth / ss);
          const span = range.to - range.from;
          const shift = (timePx / w) * span;
          try {
            ts.setVisibleLogicalRange({
              from: range.from - shift,
              to: range.to - shift,
            });
          } catch {
            /* ignore */
          }
        }

        const ps = candle.priceScale();
        const pr = ps.getVisibleRange();
        if (pr) {
          const ss = Math.max(1, landSsRef.current);
          const h = Math.max(1, el.clientHeight / ss);
          const pspan = pr.to - pr.from;
          const pshift = (pricePx / h) * pspan;
          try {
            ps.setAutoScale(false);
            ps.setVisibleRange({
              from: pr.from + pshift,
              to: pr.to + pshift,
            });
          } catch {
            /* ignore */
          }
        }
      } else if (e.touches.length === 2) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        const dist = Math.hypot(dx, dy);
        if (pinchDist > 1) {
          const scale = dist / pinchDist;
          const ts = chart.timeScale();
          const range = ts.getVisibleLogicalRange();
          const n = barsRef.current.length;
          if (range && scale > 0.01 && n > 1) {
            const mid = (range.from + range.to) / 2;
            const half = (range.to - range.from) / 2 / scale;
            if (half * 2 >= n) {
              try {
                ts.fitContent();
                candle.priceScale().setAutoScale(true);
              } catch {
                /* ignore */
              }
            } else {
              try {
                ts.setVisibleLogicalRange({
                  from: mid - half,
                  to: mid + half,
                });
              } catch {
                /* ignore */
              }
            }
          }
        }
        pinchDist = dist;
      }
    };

    const onEnd = () => {
      dragging = false;
      pinchDist = 0;
    };

    el.addEventListener("touchstart", onStart, { passive: true });
    el.addEventListener("touchmove", onMove, { passive: false });
    el.addEventListener("touchend", onEnd);
    el.addEventListener("touchcancel", onEnd);

    return () => {
      el.removeEventListener("touchstart", onStart);
      el.removeEventListener("touchmove", onMove);
      el.removeEventListener("touchend", onEnd);
      el.removeEventListener("touchcancel", onEnd);
      try {
        chart.applyOptions({
          handleScroll: {
            mouseWheel: true,
            pressedMouseMove: true,
            horzTouchDrag: true,
            vertTouchDrag: true,
          },
          handleScale: {
            axisPressedMouseMove: true,
            axisDoubleClickReset: true,
            mouseWheel: true,
            pinch: true,
          },
        });
      } catch {
        /* ignore */
      }
    };
  }, [fs, cssLandscape, loading, err]);


  const fitPanorama = () => {
    const chart = chartApi.current;
    const candle = candleApi.current;
    if (!chart) return;
    try {
      chart.timeScale().fitContent();
      candle?.priceScale().setAutoScale(true);
    } catch {
      /* ignore */
    }
  };

  const downloadBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportCsv = () => {
    const bars = aggregateBars(daily?.bars || [], period);
    if (!bars.length) return;
    const lines = ["date,open,high,low,close,volume"];
    for (const b of bars) {
      lines.push(
        [b.date, b.open, b.high, b.low, b.close, b.volume ?? ""].join(","),
      );
    }
    downloadBlob(
      new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" }),
      `${symbol}-${period}.csv`,
    );
  };

  const exportPng = () => {
    const chart = chartApi.current;
    if (!chart || typeof chart.takeScreenshot !== "function") return;
    const canvas = chart.takeScreenshot();
    canvas.toBlob((blob) => {
      if (blob) downloadBlob(blob, `${symbol}-${period}.png`);
    }, "image/png");
  };

  return (
    <div
      ref={fsRootRef}
      className={
        fs
          ? "fixed inset-0 z-[9999] bg-white"
          : "mx-auto flex max-w-[1440px] flex-col px-3 py-3 sm:px-6 sm:py-4 lg:px-8"
      }
      style={
        fs
          ? {
              // 铺满可见区（含 Safari 动态工具栏空隙）
              width: "100%",
              height: "100%",
              minHeight: "100dvh",
              minWidth: "100dvw",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
            }
          : undefined
      }
    >
      <div
        className={
          fs
            ? cssLandscape
              ? "absolute flex flex-col bg-white"
              : "flex h-full min-h-0 flex-col"
            : "contents"
        }
        style={
          fs && cssLandscape && landBox.w > 0
            ? {
                // 仅安卓伪横屏
                width: landBox.w,
                height: landBox.h,
                top: "50%",
                left: "50%",
                transform: "translate(-50%, -50%) rotate(90deg)",
                transformOrigin: "center center",
              }
            : undefined
        }
      >
      <div
        className={
          fs
            ? "flex shrink-0 items-center gap-2 border-b border-slate-100 px-2 py-1.5"
            : "mb-3 flex flex-col gap-2 lg:flex-row lg:flex-wrap lg:items-center lg:justify-between lg:gap-3"
        }
      >
        <div className="flex min-w-0 items-center gap-2 text-sm sm:gap-3">
          {fs ? (
            <button
              type="button"
              onClick={() => void exitFs()}
              className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-slate-900 text-white"
              aria-label="退出全屏"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          ) : (
            <Link
              to={`/data/symbol/${encodeURIComponent(symbol)}${overviewQuery}`}
              className="shrink-0 text-slate-500 hover:text-slate-800"
            >
              ← 返回概览
            </Link>
          )}
          {/* PC / 全屏：名称跟返回同一行；手机非全屏挪到周期行右侧 */}
          <h1
            className={`min-w-0 truncate font-bold text-slate-900 ${
              fs
                ? "text-sm"
                : "hidden text-base sm:text-lg lg:inline"
            }`}
          >
            {(daily?.name || "").trim() || symbol}
            {(daily?.name || "").trim() ? (
              <span className="ml-2 text-sm font-medium text-slate-500">
                {daily?.symbol || symbol}
              </span>
            ) : null}
          </h1>
        </div>
        <div
          className={
            fs
              ? "flex min-w-0 flex-1 items-end justify-center gap-2.5 overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
              : "flex items-end justify-between gap-2"
          }
        >
          <div className="-mx-1 flex min-w-0 flex-1 items-end gap-3 overflow-x-auto px-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden sm:mx-0 sm:gap-5 sm:overflow-visible sm:px-0 lg:flex-none">
            {PERIOD_TABS.map((t) => {
              const on = period === t.key;
              return (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => setPeriod(t.key)}
                  className={`relative shrink-0 pb-1.5 text-sm transition-colors ${
                    fs ? "pb-1 text-xs" : ""
                  } ${
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
          {/* 手机：名称/代码与周期行右对齐 */}
          {!fs ? (
            <h1 className="min-w-0 max-w-[48%] shrink-0 truncate pb-1.5 text-right text-sm font-bold text-slate-900 lg:hidden">
              {(daily?.name || "").trim() || symbol}
              {(daily?.name || "").trim() ? (
                <span className="ml-1.5 text-xs font-medium text-slate-500">
                  {daily?.symbol || symbol}
                </span>
              ) : null}
            </h1>
          ) : null}
          {fs ? (
            <button
              type="button"
              onClick={fitPanorama}
              title="全景"
              aria-label="全景"
              className="ml-auto inline-flex h-7 shrink-0 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 text-[11px] font-medium text-slate-700"
            >
              <Scan className="h-3.5 w-3.5" />
              全景
            </button>
          ) : null}
        </div>
      </div>

      <div
        className={
          fs
            ? "flex min-h-0 flex-1 flex-col px-1.5 pb-1.5 pt-1"
            : "contents"
        }
      >
        {/* 手机：指标+副图同一横滑行；PC：可换行 */}
        <div
          className={
            fs
              ? "mb-1 flex shrink-0 flex-nowrap items-center gap-1 overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
              : "mb-2 flex flex-nowrap items-center gap-1.5 overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden lg:flex-wrap lg:overflow-visible"
          }
        >
          {!fs ? (
            <span className="mr-1 shrink-0 text-[11px] font-medium text-slate-400">
              指标
            </span>
          ) : null}
          {MA_DEFS.map((d) => (
            <button
              key={d.key}
              type="button"
              onClick={() => toggleMa(d.key)}
              className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-medium tabular-nums ${
                fs ? "px-1.5 text-[10px]" : ""
              } ${
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
            className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-medium ${
              fs ? "px-1.5 text-[10px]" : ""
            } ${
              bollOn
                ? "bg-violet-50 text-violet-700 ring-1 ring-violet-200"
                : "bg-slate-50 text-slate-400"
            }`}
          >
            BOLL
          </button>
          <button
            type="button"
            onClick={exportCsv}
            title="导出 CSV"
            aria-label="导出 CSV"
            className="inline-flex shrink-0 items-center gap-0.5 rounded-md bg-slate-50 px-2 py-0.5 text-[11px] font-medium text-slate-500 hover:bg-slate-100"
          >
            <Download className="h-3 w-3" />
            CSV
          </button>
          <button
            type="button"
            onClick={exportPng}
            title="导出图片"
            aria-label="导出图片"
            className="inline-flex shrink-0 items-center gap-0.5 rounded-md bg-slate-50 px-2 py-0.5 text-[11px] font-medium text-slate-500 hover:bg-slate-100"
          >
            <ImageDown className="h-3 w-3" />
            PNG
          </button>
          <span className="mx-1 h-3 w-px shrink-0 bg-slate-200" />
          {!fs ? (
            <span className="shrink-0 text-[11px] text-slate-400">副图</span>
          ) : null}
          {(
            [
              ["none", "无"],
              ["volume", "成交量"],
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
                  ? `shrink-0 rounded-full bg-slate-900 px-2.5 py-0.5 font-semibold text-white ${
                      fs ? "px-2 text-[10px]" : "text-[11px]"
                    }`
                  : `shrink-0 rounded-full bg-slate-50 px-2.5 py-0.5 font-medium text-slate-500 hover:bg-slate-100 ${
                      fs ? "px-2 text-[10px]" : "text-[11px]"
                    }`
              }
            >
              {label}
            </button>
          ))}
        </div>

        {hover ? (
          <div
            className={
              fs
                ? "mb-1 flex shrink-0 flex-nowrap gap-x-3 overflow-x-auto text-[10px] tabular-nums text-slate-600 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
                : "mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs tabular-nums text-slate-600"
            }
          >
            <span>{hover.date}</span>
            <span>开 {Number(hover.open).toFixed(2)}</span>
            <span>高 {Number(hover.high).toFixed(2)}</span>
            <span>低 {Number(hover.low).toFixed(2)}</span>
            <span
              className={
                up
                  ? "font-semibold text-red-600"
                  : "font-semibold text-emerald-600"
              }
            >
              收 {Number(hover.close).toFixed(2)}
            </span>
            {!fs
              ? hoverInd?.map((it) => (
                  <span key={it.label} style={{ color: it.color }}>
                    {it.label} {it.value.toFixed(2)}
                  </span>
                ))
              : null}
          </div>
        ) : !fs ? (
          <div className="mb-2 h-4" />
        ) : null}

        {loading ? (
          <p className="py-24 text-center text-sm text-slate-400">加载日线…</p>
        ) : err ? (
          <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {err}
          </p>
        ) : (
          <div
            className={
              fs ? "relative min-h-0 w-full flex-1" : "relative"
            }
          >
            <div
              ref={wrapRef}
              className={
                fs
                  ? "h-full w-full overflow-hidden bg-white"
                  : "h-[min(70vh,720px)] w-full overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm"
              }
            />
            {subPane === "volume" ? (
              <div className="pointer-events-none absolute bottom-8 left-2 z-10 rounded-lg border border-slate-200/90 bg-white/90 px-2 py-0.5 text-[10px] font-medium text-slate-600 shadow-sm backdrop-blur sm:text-[11px]">
                成交量
              </div>
            ) : null}
            {/* MACD 副图线图例：区分 DIF / DEA / 柱（副图占下部约 35%） */}
            {subPane === "macd" ? (
              <div
                className="pointer-events-none absolute bottom-8 left-2 z-10 flex items-center gap-2.5 rounded-lg border border-slate-200/90 bg-white/90 px-2 py-0.5 text-[10px] font-medium text-slate-600 shadow-sm backdrop-blur sm:text-[11px]"
                aria-hidden
              >
                <span className="text-slate-400">MACD(12,26,9)</span>
                <span className="flex items-center gap-1">
                  <span
                    className="inline-block h-0.5 w-3 rounded"
                    style={{ background: "#3b82f6" }}
                  />
                  DIF
                </span>
                <span className="flex items-center gap-1">
                  <span
                    className="inline-block h-0.5 w-3 rounded"
                    style={{ background: "#f59e0b" }}
                  />
                  DEA
                </span>
                <span className="flex items-center gap-1">
                  <span
                    className="inline-block h-2.5 w-1.5 rounded-sm bg-gradient-to-b from-red-500 to-emerald-500"
                  />
                  柱
                </span>
              </div>
            ) : null}
            {/* RSI 副图图例：周期与超买超卖参考线 */}
            {subPane === "rsi" ? (
              <div
                className="pointer-events-none absolute bottom-8 left-2 z-10 flex items-center gap-2.5 rounded-lg border border-slate-200/90 bg-white/90 px-2 py-0.5 text-[10px] font-medium text-slate-600 shadow-sm backdrop-blur sm:text-[11px]"
                aria-hidden
              >
                <span className="text-slate-400">RSI(14)</span>
                <span className="flex items-center gap-1">
                  <span
                    className="inline-block h-0.5 w-3 rounded"
                    style={{ background: "#a855f7" }}
                  />
                  RSI
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block h-0 w-3 border-t border-dashed" style={{ borderColor: "rgba(225, 29, 72, 0.45)" }} />
                  70
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block h-0 w-3 border-t border-dashed" style={{ borderColor: "rgba(5, 150, 105, 0.45)" }} />
                  30
                </span>
              </div>
            ) : null}
            {/* PC：图区左上角全景 */}
            {!fs ? (
              <button
                type="button"
                onClick={fitPanorama}
                title="全景"
                aria-label="全景"
                className="absolute left-2 top-2 z-10 hidden h-8 items-center gap-1 rounded-lg border border-slate-200/90 bg-white/95 px-2 text-[11px] font-medium text-slate-600 shadow-sm backdrop-blur hover:bg-white lg:inline-flex"
              >
                <Scan className="h-3.5 w-3.5" />
                全景
              </button>
            ) : null}
            {/* 仅手机：全景；横屏按钮仅安卓（苹果靠横持自动全屏） */}
            {!fs ? (
              <div className="absolute right-2 top-2 z-10 flex items-center gap-1.5 lg:hidden">
                <button
                  type="button"
                  onClick={fitPanorama}
                  title="全景"
                  aria-label="全景"
                  className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200/90 bg-white/95 px-2 text-[11px] font-medium text-slate-600 shadow-sm backdrop-blur hover:bg-white"
                >
                  <Scan className="h-3.5 w-3.5" />
                  全景
                </button>
                {!isAppleTouchDevice() ? (
                  <button
                    type="button"
                    onClick={() => void enterFs()}
                    title="横屏全屏"
                    aria-label="横屏全屏"
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200/90 bg-white/95 text-slate-600 shadow-sm backdrop-blur hover:bg-white"
                  >
                    <Maximize2 className="h-3.5 w-3.5" />
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        )}
      </div>
      </div>
    </div>
  );
}
