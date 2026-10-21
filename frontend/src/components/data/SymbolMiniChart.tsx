import { useEffect, useRef } from "react";
import {
  AreaSeries,
  ColorType,
  createChart,
  type IChartApi,
  type Time,
} from "lightweight-charts";
import {
  fetchMarketPreviewDaily,
} from "@/lib/marketDataApi";

type Props = {
  symbol: string;
  /** 上涨用红系，下跌用绿系（A 股） */
  up?: boolean | null;
  className?: string;
  height?: number;
};

function pickTone(up: boolean | null | undefined) {
  if (up === true) {
    return {
      line: "#ef4444",
      top: "rgba(239, 68, 68, 0.28)",
      bottom: "rgba(239, 68, 68, 0.02)",
    };
  }
  if (up === false) {
    return {
      line: "#10b981",
      top: "rgba(16, 185, 129, 0.28)",
      bottom: "rgba(16, 185, 129, 0.02)",
    };
  }
  return {
    line: "#0ea5e9",
    top: "rgba(14, 165, 233, 0.28)",
    bottom: "rgba(14, 165, 233, 0.02)",
  };
}

/** 把整段数据等比例缩进视口，左右/上下留白，避免贴边截断感 */
function fitScaled(chart: IChartApi, pointCount: number) {
  const ts = chart.timeScale();
  ts.fitContent();
  // 逻辑坐标两侧各留约 2%～4% 空白
  const pad = Math.max(2, Math.round(pointCount * 0.03));
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
}

/** 预览卡内迷你走势：近一年完整曲线等比例缩小 */
export function SymbolMiniChart({
  symbol,
  up = null,
  className = "",
  height = 120,
}: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    const el = hostRef.current;
    if (!el || !symbol.trim()) return;
    let cancelled = false;

    void (async () => {
      const daily = await fetchMarketPreviewDaily(symbol).catch(() => null);
      const bars = daily?.bars || [];
      if (cancelled || !hostRef.current) return;

      chartRef.current?.remove();
      chartRef.current = null;
      if (!bars.length) return;

      const tone = pickTone(up);
      const chart = createChart(hostRef.current, {
        autoSize: true,
        height,
        layout: {
          background: { type: ColorType.Solid, color: "transparent" },
          textColor: "transparent",
          attributionLogo: false,
        },
        grid: {
          vertLines: { visible: false },
          horzLines: { visible: false },
        },
        rightPriceScale: {
          visible: false,
          borderVisible: false,
          scaleMargins: { top: 0.18, bottom: 0.18 },
        },
        leftPriceScale: { visible: false, borderVisible: false },
        timeScale: {
          visible: false,
          borderVisible: false,
          fixLeftEdge: true,
          fixRightEdge: true,
          rightOffset: 2,
        },
        crosshair: {
          vertLine: { visible: false },
          horzLine: { visible: false },
        },
        handleScroll: false,
        handleScale: false,
      });
      const series = chart.addSeries(AreaSeries, {
        lineColor: tone.line,
        topColor: tone.top,
        bottomColor: tone.bottom,
        lineWidth: 2,
        crosshairMarkerVisible: false,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      const data = bars.map((b) => ({
        time: b.date as Time,
        value: Number(b.close),
      }));
      series.setData(data);
      fitScaled(chart, data.length);
      chartRef.current = chart;
    })();

    return () => {
      cancelled = true;
      chartRef.current?.remove();
      chartRef.current = null;
    };
  }, [symbol, up, height]);

  return (
    <div
      ref={hostRef}
      className={`w-full overflow-hidden ${className}`}
      style={{ height }}
      aria-hidden
    />
  );
}
