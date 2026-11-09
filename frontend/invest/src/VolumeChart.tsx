import { useEffect, useRef } from "react";
import { ColorType, CrosshairMode, HistogramSeries, LineSeries, createChart } from "lightweight-charts";
import { useLocale } from "./i18n";

type Bar = { time: string; open: number; high: number; low: number; close: number; volume: number };

export default function VolumeChart({ bars, height = 92 }: { bars: Bar[]; height?: number }) {
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
        fontSize: 9,
        attributionLogo: false,
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: "#f4f4f4" },
      },
      crosshair: { mode: CrosshairMode.Magnet },
      rightPriceScale: { visible: false, borderVisible: false },
      timeScale: {
        visible: false,
        borderVisible: false,
        rightOffset: 2,
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      localization: { locale: locale === "en" ? "en-US" : "zh-CN" },
    });
    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "price", precision: 0, minMove: 1 },
      priceLineVisible: false,
      lastValueVisible: false,
    });
    volume.setData(
      bars.map((b) => ({
        time: b.time,
        value: b.volume,
        color: b.close >= b.open ? "rgba(230,0,18,.42)" : "rgba(22,163,74,.42)",
      })),
    );
    const addVolumeMa = (period: number, color: string) => {
      if (bars.length < period) return;
      const line = chart.addSeries(LineSeries, {
        color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      line.setData(
        bars.slice(period - 1).map((b, index) => {
          const window = bars.slice(index, index + period);
          return {
            time: b.time,
            value: window.reduce((sum, item) => sum + Number(item.volume || 0), 0) / period,
          };
        }),
      );
    };
    addVolumeMa(5, "#d97706");
    addVolumeMa(10, "#9333ea");
    chart.timeScale().fitContent();

    let disposed = false;
    const fit = () => {
      if (!disposed) chart.timeScale().fitContent();
    };
    requestAnimationFrame(fit);
    const timer = window.setTimeout(fit, 60);
    const ro = new ResizeObserver(() => {
      if (!disposed) {
        chart.applyOptions({ width: el.clientWidth || 320 });
        fit();
      }
    });
    ro.observe(el);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
      ro.disconnect();
      chart.remove();
    };
  }, [bars, height, locale]);

  if (!bars.length) return <div className="volume-empty">{t("暂无成交量", "No volume data")}</div>;
  return (
    <div
      className="volume-chart"
      ref={ref}
      role="img"
      aria-label={t(`成交量图，共 ${bars.length} 根`, `Volume chart, ${bars.length} bars`)}
    />
  );
}
