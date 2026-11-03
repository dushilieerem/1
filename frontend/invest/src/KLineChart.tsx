import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
} from "lightweight-charts";
import { useLocale } from "./i18n";

type Bar = { time: string; open: number; high: number; low: number; close: number; volume: number };
type Line = { time: string; value: number };

export default function KLineChart({
  bars,
  ma5 = [],
  ma10 = [],
  ma20 = [],
  height = 260,
}: {
  bars: Bar[];
  ma5?: Line[];
  ma10?: Line[];
  ma20?: Line[];
  height?: number;
}) {
  const { t, locale } = useLocale();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current || !bars.length) return;
    const el = ref.current;
    const chart = createChart(el, {
      width: el.clientWidth || 320,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#8a8a8a",
        fontSize: 10,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "#f4f4f4" },
        horzLines: { color: "#f4f4f4" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.08, bottom: 0.24 } },
      timeScale: {
        borderVisible: false,
        timeVisible: false,
        secondsVisible: false,
        rightOffset: 2,
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      localization: { locale: locale === "en" ? "en-US" : "zh-CN" },
    });

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

    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "price", precision: 0, minMove: 1 },
      priceScaleId: "volume",
      priceLineVisible: false,
      lastValueVisible: false,
    });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volume.priceScale().applyOptions({ visible: false });
    volume.setData(
      bars.map((b) => ({
        time: b.time,
        value: b.volume,
        color: b.close >= b.open ? "rgba(230,0,18,.42)" : "rgba(22,163,74,.42)",
      })),
    );
    volume.applyOptions({ lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false, title: "" });

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
    addLine(ma5, "#d97706");
    addLine(ma10, "#9333ea");
    addLine(ma20, "#2563eb");

    chart.timeScale().fitContent();

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
      chart.remove();
    };
  }, [bars, ma5, ma10, ma20, height, locale]);

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
