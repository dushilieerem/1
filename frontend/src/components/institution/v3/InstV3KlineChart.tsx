import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  type IChartApi,
  type Time,
} from "lightweight-charts";
import type { V3Bar } from "@/lib/instV3Api";

type Point = { time: Time; value: number };

function sma(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = [];
  let sum = 0;
  for (let i = 0; i < values.length; i += 1) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    out.push(i >= period - 1 ? sum / period : null);
  }
  return out;
}

function ema(values: number[], period: number): number[] {
  if (!values.length) return [];
  const alpha = 2 / (period + 1);
  const out = [values[0]];
  for (let i = 1; i < values.length; i += 1) {
    out.push(alpha * values[i] + (1 - alpha) * out[i - 1]);
  }
  return out;
}

function boll(closes: number[], period = 20, mult = 2) {
  const mid = sma(closes, period);
  const upper: (number | null)[] = [];
  const lower: (number | null)[] = [];
  for (let i = 0; i < closes.length; i += 1) {
    const m = mid[i];
    if (m == null) {
      upper.push(null);
      lower.push(null);
      continue;
    }
    const slice = closes.slice(i - period + 1, i + 1);
    const variance = slice.reduce((sum, value) => sum + (value - m) ** 2, 0) / period;
    const sd = Math.sqrt(variance);
    upper.push(m + mult * sd);
    lower.push(m - mult * sd);
  }
  return { mid, upper, lower };
}

function macd(closes: number[]) {
  const fast = ema(closes, 12);
  const slow = ema(closes, 26);
  const dif = closes.map((_, i) => fast[i] - slow[i]);
  const dea = ema(dif, 9);
  const hist = dif.map((value, i) => (value - dea[i]) * 2);
  return { dif, dea, hist };
}

function kdj(bars: V3Bar[], period = 9) {
  const k: number[] = [];
  const d: number[] = [];
  const j: number[] = [];
  let prevK = 50;
  let prevD = 50;
  for (let i = 0; i < bars.length; i += 1) {
    const slice = bars.slice(Math.max(0, i - period + 1), i + 1);
    const low = Math.min(...slice.map((b) => Number(b.low)));
    const high = Math.max(...slice.map((b) => Number(b.high)));
    const close = Number(bars[i].close);
    const rsv = high === low ? 50 : ((close - low) / (high - low)) * 100;
    prevK = (2 * prevK + rsv) / 3;
    prevD = (2 * prevD + prevK) / 3;
    k.push(prevK);
    d.push(prevD);
    j.push(3 * prevK - 2 * prevD);
  }
  return { k, d, j };
}

function lineData(times: string[], values: (number | null)[]): Point[] {
  const out: Point[] = [];
  values.forEach((value, i) => {
    if (value != null && Number.isFinite(value)) out.push({ time: times[i] as Time, value });
  });
  return out;
}

export function InstV3KlineChart({ bars, height = 500 }: { bars: V3Bar[]; height?: number }) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [showMA, setShowMA] = useState(true);
  const [showBoll, setShowBoll] = useState(true);
  const [showMacd, setShowMacd] = useState(true);
  const [showKdj, setShowKdj] = useState(true);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    chartRef.current?.remove();

    const ordered = [...bars]
      .filter((b) => b.trade_date && Number.isFinite(Number(b.close)))
      .sort((a, b) => String(a.trade_date).localeCompare(String(b.trade_date)));
    if (!ordered.length) return;
    const times = ordered.map((b) => String(b.trade_date).slice(0, 10));
    const closes = ordered.map((b) => Number(b.close));

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

    const addLine = (color: string, width: 1 | 2 = 1, dashed = false) =>
      chart.addSeries(LineSeries, {
        color,
        lineWidth: width,
        lineStyle: dashed ? LineStyle.Dashed : LineStyle.Solid,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });

    if (showMA) {
      for (const [period, color] of [
        [5, "#d4a017"],
        [10, "#8e5aa8"],
        [20, "#2e86ab"],
        [60, "#7f8c8d"],
      ] as const) {
        addLine(color, 1).setData(lineData(times, sma(closes, period)));
      }
    }
    if (showBoll) {
      const b = boll(closes);
      addLine("#b07aa1", 1, true).setData(lineData(times, b.mid));
      addLine("#c9b3bf", 1, true).setData(lineData(times, b.upper));
      addLine("#c9b3bf", 1, true).setData(lineData(times, b.lower));
    }

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

    const subPanes: Array<{ setHeight: (h: number) => void }> = [];
    if (showMacd) {
      const pane = chart.addPane();
      pane.setHeight(100);
      subPanes.push(pane);
      const paneIndex = chart.panes().length - 1;
      const m = macd(closes);
      chart
        .addSeries(LineSeries, { color: "#c0392b", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, paneIndex)
        .setData(lineData(times, m.dif));
      chart
        .addSeries(LineSeries, { color: "#2e86ab", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, paneIndex)
        .setData(lineData(times, m.dea));
      chart
        .addSeries(
          HistogramSeries,
          { priceLineVisible: false, lastValueVisible: false },
          paneIndex,
        )
        .setData(
          m.hist.map((value, i) => ({
            time: times[i] as Time,
            value,
            color: value >= 0 ? "#e7b8b2" : "#b7d8c6",
          })),
        );
    }
    if (showKdj) {
      const pane = chart.addPane();
      pane.setHeight(100);
      subPanes.push(pane);
      const paneIndex = chart.panes().length - 1;
      const k = kdj(ordered);
      chart
        .addSeries(LineSeries, { color: "#c0392b", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, paneIndex)
        .setData(lineData(times, k.k));
      chart
        .addSeries(LineSeries, { color: "#2e86ab", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, paneIndex)
        .setData(lineData(times, k.d));
      chart
        .addSeries(LineSeries, { color: "#d4a017", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, paneIndex)
        .setData(lineData(times, k.j));
    }

    const mainHeight = Math.max(220, height - subPanes.length * 100 - 20);
    chart.panes()[0]?.setHeight(mainHeight);

    chart.timeScale().fitContent();
    chartRef.current = chart;
    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [bars, height, showMA, showBoll, showMacd, showKdj]);

  const toggle = (label: string, on: boolean, set: (v: boolean) => void) => (
    <button type="button" className={`v3-kline-tool${on ? " on" : ""}`} onClick={() => set(!on)}>
      {label}
    </button>
  );

  return (
    <div>
      <div className="v3-kline-tools">
        {toggle("MA", showMA, setShowMA)}
        {toggle("BOLL", showBoll, setShowBoll)}
        {toggle("MACD", showMacd, setShowMacd)}
        {toggle("KDJ", showKdj, setShowKdj)}
      </div>
      <div ref={hostRef} style={{ width: "100%", height }} />
    </div>
  );
}
