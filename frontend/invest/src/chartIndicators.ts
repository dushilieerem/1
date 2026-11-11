import type { Time } from "lightweight-charts";

export type Bar = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount?: number;
};

export type Point = { time: Time; value: number };
export type SubIndicator = "volume" | "amount" | "macd" | "kdj" | "rsi";

export function linePoints(bars: Bar[], values: Array<number | null>): Point[] {
  const out: Point[] = [];
  bars.forEach((bar, i) => {
    const value = values[i];
    if (value != null && Number.isFinite(value)) out.push({ time: bar.time as Time, value });
  });
  return out;
}

export function movingAverage(values: number[], period: number): Array<number | null> {
  const out: Array<number | null> = values.map(() => null);
  let sum = 0;
  for (let i = 0; i < values.length; i += 1) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    if (i >= period - 1) out[i] = sum / period;
  }
  return out;
}

function ema(values: number[], period: number): number[] {
  if (!values.length) return [];
  const k = 2 / (period + 1);
  const out = [values[0]];
  for (let i = 1; i < values.length; i += 1) out.push(values[i] * k + out[i - 1] * (1 - k));
  return out;
}

export function macd(bars: Bar[]): { dif: Point[]; dea: Point[]; hist: Point[] } {
  const closes = bars.map((b) => Number(b.close));
  if (!closes.length) return { dif: [], dea: [], hist: [] };
  const e12 = ema(closes, 12);
  const e26 = ema(closes, 26);
  const difValues = closes.map((_, i) => e12[i] - e26[i]);
  const deaValues = ema(difValues, 9);
  const histValues = difValues.map((v, i) => 2 * (v - deaValues[i]));
  return {
    dif: linePoints(bars, difValues),
    dea: linePoints(bars, deaValues),
    hist: linePoints(bars, histValues),
  };
}

export function kdj(bars: Bar[]): { k: Point[]; d: Point[]; j: Point[] } {
  let kPrev = 50;
  let dPrev = 50;
  const ks: Array<number | null> = [];
  const ds: Array<number | null> = [];
  const js: Array<number | null> = [];
  bars.forEach((bar, i) => {
    if (i < 8) {
      ks.push(null);
      ds.push(null);
      js.push(null);
      return;
    }
    const window = bars.slice(i - 8, i + 1);
    const low = Math.min(...window.map((b) => Number(b.low)));
    const high = Math.max(...window.map((b) => Number(b.high)));
    const rsv = high === low ? 50 : ((Number(bar.close) - low) / (high - low)) * 100;
    kPrev = (2 / 3) * kPrev + (1 / 3) * rsv;
    dPrev = (2 / 3) * dPrev + (1 / 3) * kPrev;
    ks.push(kPrev);
    ds.push(dPrev);
    js.push(3 * kPrev - 2 * dPrev);
  });
  return { k: linePoints(bars, ks), d: linePoints(bars, ds), j: linePoints(bars, js) };
}

export function rsi(bars: Bar[], period: number): Point[] {
  const closes = bars.map((b) => Number(b.close));
  const values: Array<number | null> = closes.map(() => null);
  let gain = 0;
  let loss = 0;
  for (let i = 1; i < closes.length; i += 1) {
    const change = closes[i] - closes[i - 1];
    if (i <= period) {
      if (change > 0) gain += change;
      else loss -= change;
      if (i === period) {
        const avgGain = gain / period;
        const avgLoss = loss / period;
        values[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
      }
    } else {
      gain = (gain * (period - 1) + Math.max(change, 0)) / period;
      loss = (loss * (period - 1) + Math.max(-change, 0)) / period;
      values[i] = loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
    }
  }
  return linePoints(bars, values);
}

export function latestValue(points: Point[]): number | null {
  return points.length ? Number(points[points.length - 1].value) : null;
}

export function formatCompact(value: number | null, unit: "vol" | "amount" | "ratio" | "index"): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (unit === "vol") return `${(value / 1e4).toFixed(1)} 万`;
  if (unit === "amount") return `${(value / 1e8).toFixed(2)} 亿`;
  if (unit === "index") return value.toFixed(2);
  return value.toFixed(3);
}

export const SUB_INDICATORS: Array<{ key: SubIndicator; zh: string; en: string }> = [
  { key: "volume", zh: "成交量", en: "Volume" },
  { key: "amount", zh: "成交额", en: "Turnover" },
  { key: "macd", zh: "MACD", en: "MACD" },
  { key: "kdj", zh: "KDJ", en: "KDJ" },
  { key: "rsi", zh: "RSI", en: "RSI" },
];


export function chartTick(time: Time | { year: number; month: number; day: number }): string {
  if (typeof time === "string") return time.slice(0, 10);
  if ("year" in time) return `${time.year}-${String(time.month).padStart(2, "0")}-${String(time.day).padStart(2, "0")}`;
  return String(time);
}

export function aggregateBars(bars: Bar[], period: "daily" | "weekly" | "monthly"): Bar[] {
  if (period === "daily") return bars;
  const groups = new Map<string, Bar[]>();
  for (const bar of bars) {
    const d = new Date(`${String(bar.time).slice(0, 10)}T00:00:00`);
    if (Number.isNaN(d.getTime())) continue;
    const week = Math.ceil((((d.getTime() - new Date(d.getFullYear(), 0, 1).getTime()) / 86400000) + new Date(d.getFullYear(), 0, 1).getDay() + 1) / 7);
    const key = period === "weekly" ? `${d.getFullYear()}-W${String(week).padStart(2, "0")}` : `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    const group = groups.get(key) || [];
    group.push(bar);
    groups.set(key, group);
  }
  return Array.from(groups.values()).map((group) => ({
    time: group[group.length - 1].time,
    open: group[0].open,
    high: Math.max(...group.map((b) => b.high)),
    low: Math.min(...group.map((b) => b.low)),
    close: group[group.length - 1].close,
    volume: group.reduce((sum, b) => sum + (b.volume || 0), 0),
    amount: group.reduce((sum, b) => sum + (b.amount || 0), 0),
  }));
}
