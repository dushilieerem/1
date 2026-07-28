import { useEffect, useRef } from "react";
import {
  AreaSeries,
  ColorType,
  createChart,
  type IChartApi,
  type Time,
} from "lightweight-charts";
import {
  fetchMarketDaily,
  panelLookbackStart,
  type MarketBar,
} from "@/lib/marketDataApi";

type Props = {
  symbol: string;
  /** 上涨用红系，下跌用绿系（A 股） */
  up?: boolean | null;
  /** 若已知数据末日，可少打一轮试探请求 */
  asOf?: string | null;
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

/** 近一年交易日（约 250 根），保证预览是完整一年再缩放进卡片 */
async function loadOneYearBars(
  symbol: string,
  asOfHint?: string | null,
): Promise<MarketBar[]> {
  try {
    let asOf = asOfHint || null;
    if (!asOf) {
      const tip = await fetchMarketDaily(symbol, { start: "2025-01-01" });
      asOf =
        tip.date_range?.end ||
        (tip.bars.length ? tip.bars[tip.bars.length - 1].date : null);
    }
    if (asOf) {
      const start = panelLookbackStart(asOf, 370);
      const near = await fetchMarketDaily(symbol, { start, end: asOf });
      if (near.bars?.length) return near.bars;
    }
  } catch {
    // fall through
  }
  try {
    const full = await fetchMarketDaily(symbol);
    const bars = full.bars || [];
    if (!bars.length) return [];
    const end = bars[bars.length - 1].date;
    const start = panelLookbackStart(end, 370);
    return bars.filter((b) => b.date >= start);
  } catch {
    return [];
  }
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
  asOf = null,
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
      const bars = await loadOneYearBars(symbol, asOf);
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
        lineWidth: 1.5,
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
  }, [symbol, up, asOf, height]);

  return (
    <div
      ref={hostRef}
      className={`w-full overflow-hidden ${className}`}
      style={{ height }}
      aria-hidden
    />
  );
}
