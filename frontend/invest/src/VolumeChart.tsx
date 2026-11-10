import { useEffect, useRef } from "react";
import {
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
} from "lightweight-charts";
import { useLocale } from "./i18n";
import { chartTick } from "./chartIndicators";
import {
  type Bar,
  type Point,
  type SubIndicator,
  kdj,
  macd,
  movingAverage,
  rsi,
} from "./chartIndicators";

type Range = { from: number; to: number };

export default function VolumeChart({
  bars,
  indicator = "volume",
  height = 118,
  range,
  onRangeChange,
}: {
  bars: Bar[];
  indicator?: SubIndicator;
  height?: number;
  range?: Range | null;
  onRangeChange?: (range: Range | null) => void;
}) {
  const { t, locale } = useLocale();
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const applyingRange = useRef(false);
  const rangeRef = useRef(range);
  const rangeHandler = useRef(onRangeChange);
  rangeRef.current = range;
  rangeHandler.current = onRangeChange;

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
        vertLines: { visible: false },
        horzLines: { color: "#f4f4f4" },
      },
      crosshair: { mode: CrosshairMode.Magnet },
      rightPriceScale: { visible: true, borderVisible: false, minimumWidth: 80, scaleMargins: { top: 0.12, bottom: 0.12 } },
      timeScale: {
        visible: true,
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

    const addLine = (points: Point[], color: string, width = 1) => {
      if (!points.length) return;
      const line = chart.addSeries(LineSeries, {
        color,
        lineWidth: width,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      line.setData(points);
    };

    if (indicator === "volume" || indicator === "amount") {
      const values = bars.map((b) => Number((indicator === "volume" ? b.volume : b.amount) || 0));
      const ma5 = movingAverage(values, 5);
      const ma10 = movingAverage(values, 10);
      const histogram = chart.addSeries(HistogramSeries, {
        priceFormat: { type: "price", precision: 0, minMove: 1 },
        priceLineVisible: false,
        lastValueVisible: false,
      });
      histogram.setData(
        bars.map((b) => ({
          time: b.time,
          value: Number((indicator === "volume" ? b.volume : b.amount) || 0),
          color: b.close >= b.open ? "rgba(230,0,18,.42)" : "rgba(22,163,74,.42)",
        })),
      );
      addLine(
        values.map((_, i) => ({ time: bars[i].time as any, value: ma5[i] })).filter((x: any) => x.value != null),
        "#d97706",
      );
      addLine(
        values.map((_, i) => ({ time: bars[i].time as any, value: ma10[i] })).filter((x: any) => x.value != null),
        "#9333ea",
      );
    } else if (indicator === "macd") {
      const data = macd(bars);
      const hist = chart.addSeries(HistogramSeries, {
        priceFormat: { type: "price", precision: 2, minMove: 0.01 },
        priceLineVisible: false,
        lastValueVisible: false,
      });
      hist.setData(data.hist.map((p) => ({ time: p.time, value: p.value, color: p.value >= 0 ? "rgba(230,0,18,.5)" : "rgba(22,163,74,.5)" })));
      addLine(data.dif, "#2563eb");
      addLine(data.dea, "#d97706");
    } else if (indicator === "kdj") {
      const data = kdj(bars);
      addLine(data.k, "#2563eb");
      addLine(data.d, "#d97706");
      addLine(data.j, "#9333ea");
    } else {
      addLine(rsi(bars, 6), "#2563eb");
      addLine(rsi(bars, 12), "#d97706");
      addLine(rsi(bars, 24), "#9333ea");
    }

    chart.timeScale().fitContent();
    const apply = (next: Range | null) => {
      if (!next) return;
      applyingRange.current = true;
      chart.timeScale().setVisibleLogicalRange(next);
      requestAnimationFrame(() => { applyingRange.current = false; });
    };
    apply(rangeRef.current || null);
    const onVisibleRange = (next: { from: number; to: number } | null) => {
      if (!next || applyingRange.current) return;
      rangeHandler.current?.({ from: next.from, to: next.to });
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(onVisibleRange);

    let disposed = false;
    const timer = window.setTimeout(() => {
      if (!disposed && !rangeRef.current) chart.timeScale().fitContent();
    }, 60);
    const ro = new ResizeObserver(() => {
      if (!disposed) {
        chart.applyOptions({ width: el.clientWidth || 320 });
        if (!rangeRef.current) chart.timeScale().fitContent();
      }
    });
    ro.observe(el);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
      ro.disconnect();
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onVisibleRange);
      chart.remove();
      chartRef.current = null;
    };
  }, [bars, indicator, height, locale]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !range) return;
    applyingRange.current = true;
    chart.timeScale().setVisibleLogicalRange(range);
    requestAnimationFrame(() => { applyingRange.current = false; });
  }, [range]);

  if (!bars.length) return <div className="volume-empty">{t("暂无副图数据", "No sub-chart data")}</div>;
  return (
    <div
      className="volume-chart"
      ref={ref}
      role="img"
      aria-label={t(`副图：${indicator}`, `Sub-chart: ${indicator}`)}
    />
  );
}
