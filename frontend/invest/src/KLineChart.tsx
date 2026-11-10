import { useEffect, useMemo, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  LineSeries,
  createChart,
} from "lightweight-charts";
import { useLocale } from "./i18n";
import { chartTick } from "./chartIndicators";

type Bar = { time: string; open: number; high: number; low: number; close: number; volume: number };
type Line = { time: string; value: number };

export default function KLineChart({
  bars,
  ma5 = [],
  ma10 = [],
  ma20 = [],
  height = 230,
  indicator = "ma",
  range,
  onRangeChange,
}: {
  bars: Bar[];
  ma5?: Line[];
  ma10?: Line[];
  ma20?: Line[];
  height?: number;
  indicator?: "ma" | "boll";
  range?: { from: number; to: number } | null;
  onRangeChange?: (range: { from: number; to: number } | null) => void;
}) {
  const { t, locale } = useLocale();
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const applyingRange = useRef(false);
  const rangeRef = useRef(range);
  const rangeHandler = useRef(onRangeChange);
  rangeRef.current = range;
  rangeHandler.current = onRangeChange;
  const boll = useMemo(() => {
    if (indicator !== "boll" || bars.length < 20) return { mid: [], up: [], low: [] };
    const mid: Line[] = [];
    const up: Line[] = [];
    const low: Line[] = [];
    for (let i = 19; i < bars.length; i += 1) {
      const closes = bars.slice(i - 19, i + 1).map((b) => Number(b.close));
      const mean = closes.reduce((sum, value) => sum + value, 0) / closes.length;
      const variance = closes.reduce((sum, value) => sum + (value - mean) ** 2, 0) / closes.length;
      const sd = Math.sqrt(variance);
      mid.push({ time: bars[i].time, value: mean });
      up.push({ time: bars[i].time, value: mean + 2 * sd });
      low.push({ time: bars[i].time, value: mean - 2 * sd });
    }
    return { mid, up, low };
  }, [bars, indicator]);

  useEffect(() => {
    if (!ref.current || !bars.length) return;
    const el = ref.current;
    const chart = createChart(el, {
      width: el.clientWidth || 320,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#8a8a8a",
        fontSize: 9,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "#f4f4f4" },
        horzLines: { color: "#f4f4f4" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderVisible: false, minimumWidth: 80, scaleMargins: { top: 0.08, bottom: 0.08 } },
      timeScale: {
        borderVisible: false,
        timeVisible: false,
        secondsVisible: false,
        rightOffset: 2,
        fixLeftEdge: true,
        fixRightEdge: true,
        tickMarkFormatter: chartTick,
      },
      localization: { locale: locale === "en" ? "en-US" : "zh-CN" },
    });

    chartRef.current = chart;
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: "#e60012",
      downColor: "#16a34a",
      borderVisible: false,
      wickUpColor: "#e60012",
      wickDownColor: "#16a34a",
      priceLineVisible: false,
      lastValueVisible: false,
    });
    candle.setData(bars.map((b) => ({ time: b.time, open: b.open, high: b.high, low: b.low, close: b.close })));

    const addLine = (data: Line[], color: string) => {
      if (!data.length) return;
      const line = chart.addSeries(LineSeries, {
        color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      line.setData(data.map((d) => ({ time: d.time, value: d.value })));
    };
    if (indicator === "boll") {
      addLine(boll.mid, "#d97706");
      addLine(boll.up, "#e60012");
      addLine(boll.low, "#2563eb");
    } else {
      addLine(ma5, "#d97706");
      addLine(ma10, "#9333ea");
      addLine(ma20, "#2563eb");
    }

    chart.timeScale().fitContent();
    if (rangeRef.current) {
      applyingRange.current = true;
      chart.timeScale().setVisibleLogicalRange(rangeRef.current);
      requestAnimationFrame(() => { applyingRange.current = false; });
    }
    const onVisibleRange = (next: { from: number; to: number } | null) => {
      if (!next || applyingRange.current) return;
      rangeHandler.current?.({ from: next.from, to: next.to });
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(onVisibleRange);

    let disposed = false;
    const fit = () => {
      if (disposed) return;
      chart.timeScale().fitContent();
    };
    requestAnimationFrame(fit);
    const fitTimer = window.setTimeout(fit, 60);

    const ro = new ResizeObserver(() => {
      if (disposed) return;
      chart.applyOptions({ width: el.clientWidth || 320 });
      fit();
    });
    ro.observe(el);

    return () => {
      disposed = true;
      window.clearTimeout(fitTimer);
      ro.disconnect();
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onVisibleRange);
      chart.remove();
      chartRef.current = null;
    };
  }, [bars, ma5, ma10, ma20, boll, indicator, height, locale]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !range) return;
    applyingRange.current = true;
    chart.timeScale().setVisibleLogicalRange(range);
    requestAnimationFrame(() => { applyingRange.current = false; });
  }, [range]);

  if (!bars.length) return <div className="kline-empty">{t("暂无行情数据", "No market data")}</div>;
  return (
    <div
      className="kline"
      ref={ref}
      role="img"
      aria-label={t(
        `K 线图，共 ${bars.length} 根，最新收盘 ${bars[bars.length - 1]?.close}`,
        `K-line chart, ${bars.length} bars, latest close ${bars[bars.length - 1]?.close}`,
      )}
    />
  );
}
