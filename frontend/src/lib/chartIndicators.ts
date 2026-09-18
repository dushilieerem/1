/** 日线 OHLC 指标（前端计算；无 volume）。 */

export type OhlcPoint = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type LinePoint = { time: string; value: number };

export type HistPoint = { time: string; value: number; color?: string };

export const MA_DEFS = [
  { key: "ma5", period: 5, label: "MA5", color: "#f59e0b", defaultOn: true },
  { key: "ma10", period: 10, label: "MA10", color: "#3b82f6", defaultOn: true },
  { key: "ma20", period: 20, label: "MA20", color: "#a855f7", defaultOn: true },
  { key: "ma60", period: 60, label: "MA60", color: "#0d9488", defaultOn: true },
  { key: "ma120", period: 120, label: "MA120", color: "#64748b", defaultOn: false },
  { key: "ma250", period: 250, label: "MA250", color: "#94a3b8", defaultOn: false },
] as const;

export type MaKey = (typeof MA_DEFS)[number]["key"];

export function smaSeries(
  bars: OhlcPoint[],
  period: number,
): LinePoint[] {
  const out: LinePoint[] = [];
  if (period < 1 || bars.length < period) return out;
  let sum = 0;
  for (let i = 0; i < bars.length; i++) {
    sum += Number(bars[i].close);
    if (i >= period) sum -= Number(bars[i - period].close);
    if (i >= period - 1) {
      out.push({ time: bars[i].date, value: sum / period });
    }
  }
  return out;
}

/** BOLL(period, mult)：中轨 SMA，上下轨 = 中轨 ± mult * 标准差 */
export function bollinger(
  bars: OhlcPoint[],
  period = 20,
  mult = 2,
): { mid: LinePoint[]; upper: LinePoint[]; lower: LinePoint[] } {
  const mid: LinePoint[] = [];
  const upper: LinePoint[] = [];
  const lower: LinePoint[] = [];
  if (bars.length < period) return { mid, upper, lower };
  for (let i = period - 1; i < bars.length; i++) {
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += Number(bars[j].close);
    const mean = sum / period;
    let varSum = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const d = Number(bars[j].close) - mean;
      varSum += d * d;
    }
    const std = Math.sqrt(varSum / period);
    const t = bars[i].date;
    mid.push({ time: t, value: mean });
    upper.push({ time: t, value: mean + mult * std });
    lower.push({ time: t, value: mean - mult * std });
  }
  return { mid, upper, lower };
}

function emaArray(closes: number[], period: number): (number | null)[] {
  const out: (number | null)[] = Array(closes.length).fill(null);
  if (closes.length < period) return out;
  const k = 2 / (period + 1);
  let ema = 0;
  for (let i = 0; i < period; i++) ema += closes[i];
  ema /= period;
  out[period - 1] = ema;
  for (let i = period; i < closes.length; i++) {
    ema = closes[i] * k + ema * (1 - k);
    out[i] = ema;
  }
  return out;
}

/** MACD(12,26,9)：DIF / DEA / HIST */
export function macd(
  bars: OhlcPoint[],
  fast = 12,
  slow = 26,
  signal = 9,
): { dif: LinePoint[]; dea: LinePoint[]; hist: HistPoint[] } {
  const closes = bars.map((b) => Number(b.close));
  const emaFast = emaArray(closes, fast);
  const emaSlow = emaArray(closes, slow);
  const difRaw: (number | null)[] = closes.map((_, i) => {
    if (emaFast[i] == null || emaSlow[i] == null) return null;
    return (emaFast[i] as number) - (emaSlow[i] as number);
  });
  const dif: LinePoint[] = [];
  const dea: LinePoint[] = [];
  const hist: HistPoint[] = [];
  if (difRaw.every((v) => v == null)) return { dif, dea, hist };

  const deaArr: (number | null)[] = Array(closes.length).fill(null);
  let seed = 0;
  let seeded = 0;
  let lastDea: number | null = null;
  const k = 2 / (signal + 1);
  for (let i = 0; i < closes.length; i++) {
    if (difRaw[i] == null) continue;
    if (seeded < signal) {
      seed += difRaw[i] as number;
      seeded++;
      if (seeded === signal) {
        lastDea = seed / signal;
        deaArr[i] = lastDea;
      }
      continue;
    }
    lastDea = (difRaw[i] as number) * k + (lastDea as number) * (1 - k);
    deaArr[i] = lastDea;
  }

  for (let i = 0; i < bars.length; i++) {
    if (difRaw[i] == null) continue;
    const d = difRaw[i] as number;
    dif.push({ time: bars[i].date, value: d });
    if (deaArr[i] != null) {
      const e = deaArr[i] as number;
      dea.push({ time: bars[i].date, value: e });
      const h = d - e;
      hist.push({
        time: bars[i].date,
        value: h,
        color: h >= 0 ? "rgba(225, 29, 72, 0.55)" : "rgba(5, 150, 105, 0.55)",
      });
    }
  }
  return { dif, dea, hist };
}

/** RSI(period) Wilder */
export function rsi(bars: OhlcPoint[], period = 14): LinePoint[] {
  const out: LinePoint[] = [];
  if (bars.length <= period) return out;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i++) {
    const ch = Number(bars[i].close) - Number(bars[i - 1].close);
    if (ch >= 0) gain += ch;
    else loss -= ch;
  }
  let avgGain = gain / period;
  let avgLoss = loss / period;
  const push = (i: number) => {
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    const val = avgLoss === 0 ? 100 : 100 - 100 / (1 + rs);
    out.push({ time: bars[i].date, value: val });
  };
  push(period);
  for (let i = period + 1; i < bars.length; i++) {
    const ch = Number(bars[i].close) - Number(bars[i - 1].close);
    const g = ch > 0 ? ch : 0;
    const l = ch < 0 ? -ch : 0;
    avgGain = (avgGain * (period - 1) + g) / period;
    avgLoss = (avgLoss * (period - 1) + l) / period;
    push(i);
  }
  return out;
}

/** 按日期过滤已算好的线点 */
export function filterLineByDates(
  points: LinePoint[],
  dates: Set<string>,
): LinePoint[] {
  return points.filter((p) => dates.has(p.time));
}

export function filterHistByDates(
  points: HistPoint[],
  dates: Set<string>,
): HistPoint[] {
  return points.filter((p) => dates.has(p.time));
}
