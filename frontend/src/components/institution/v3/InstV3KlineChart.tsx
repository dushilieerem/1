import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  createChart,
  type IChartApi,
  type Time,
} from "lightweight-charts";
import type { V3Bar } from "@/lib/instV3Api";

/** 机构端 K 线：A 股红涨绿跌，成交量副图；数据来自 /api/inst/stocks/{id}/bars。 */
export function InstV3KlineChart({ bars, height = 360 }: { bars: V3Bar[]; height?: number }) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    chartRef.current?.remove();
    const chart = createChart(host, {
      autoSize: true,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#6b6370",
        attributionLogo: false,
        fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif",
        fontSize: 12,
      },
      grid: {
        vertLines: { color: "#f3eef5" },
        horzLines: { color: "#f3eef5" },
      },
      rightPriceScale: {
        borderColor: "#e8dfe9",
        scaleMargins: { top: 0.08, bottom: 0.24 },
      },
      timeScale: {
        borderColor: "#e8dfe9",
        timeVisible: false,
        rightOffset: 3,
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "#c9b3bf", width: 1, style: 3 },
        horzLine: { color: "#c9b3bf", width: 1, style: 3 },
      },
    });

    const ordered = [...bars]
      .filter((b) => b.trade_date && Number.isFinite(Number(b.close)))
      .sort((a, b) => String(a.trade_date).localeCompare(String(b.trade_date)));
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#c0392b",
      downColor: "#1e8449",
      borderUpColor: "#c0392b",
      borderDownColor: "#1e8449",
      wickUpColor: "#c0392b",
      wickDownColor: "#1e8449",
    });
    candles.setData(
      ordered.map((b) => ({
        time: String(b.trade_date).slice(0, 10) as Time,
        open: Number(b.open),
        high: Number(b.high),
        low: Number(b.low),
        close: Number(b.close),
      })),
    );

    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
      lastValueVisible: false,
      priceLineVisible: false,
    });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volume.setData(
      ordered.map((b) => ({
        time: String(b.trade_date).slice(0, 10) as Time,
        value: Number(b.volume || 0),
        color: Number(b.close) >= Number(b.open) ? "#e7b8b2" : "#b7d8c6",
      })),
    );

    chart.timeScale().fitContent();
    chartRef.current = chart;
    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [bars, height]);

  return <div ref={hostRef} style={{ width: "100%", height }} />;
}
