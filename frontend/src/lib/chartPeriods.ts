import type { MarketBar } from "@/lib/marketDataApi";

export type PeriodKey = "day" | "week" | "month" | "quarter" | "year";

export const PERIOD_TABS: { key: PeriodKey; label: string }[] = [
  { key: "day", label: "日K" },
  { key: "week", label: "周K" },
  { key: "month", label: "月K" },
  { key: "quarter", label: "季K" },
  { key: "year", label: "年K" },
];

const CN_WEEKDAY = ["日", "一", "二", "三", "四", "五", "六"] as const;

function ymdLocal(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** 同花顺风格十字轴日期：2026-01-16 星期四 */
export function formatThsCrosshairDate(time: string | number | { year: number; month: number; day: number }): string {
  const raw =
    typeof time === "object" && time && "year" in time
      ? `${time.year}-${String(time.month).padStart(2, "0")}-${String(time.day).padStart(2, "0")}`
      : String(time);
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(raw);
  if (!m) return raw;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  const dt = new Date(y, mo - 1, d);
  return `${m[1]}-${m[2]}-${m[3]} 星期${CN_WEEKDAY[dt.getDay()]}`;
}

/** 周期分桶键（周=当周周一） */
export function periodBucket(date: string, period: PeriodKey): string {
  if (period === "day") return date;
  const [ys, ms, ds] = date.split("-");
  const y = Number(ys);
  const m = Number(ms);
  const d = Number(ds);
  if (period === "month") return `${ys}-${ms}`;
  if (period === "quarter") return `${y}-Q${Math.floor((m - 1) / 3) + 1}`;
  if (period === "year") return ys;
  const dt = new Date(y, m - 1, d);
  const dow = dt.getDay();
  const mondayOffset = dow === 0 ? -6 : 1 - dow;
  const mon = new Date(dt);
  mon.setDate(dt.getDate() + mondayOffset);
  return ymdLocal(mon);
}

/** 日线 → 周/月/季/年 OHLC（时间为该周期最后交易日） */
export function aggregateBars(bars: MarketBar[], period: PeriodKey): MarketBar[] {
  if (!bars.length || period === "day") return bars;
  const order: string[] = [];
  const groups = new Map<string, MarketBar[]>();
  for (const b of bars) {
    const k = periodBucket(b.date, period);
    let g = groups.get(k);
    if (!g) {
      g = [];
      groups.set(k, g);
      order.push(k);
    }
    g.push(b);
  }
  return order.map((k) => {
    const g = groups.get(k)!;
    let high = Number(g[0].high);
    let low = Number(g[0].low);
    for (let i = 1; i < g.length; i++) {
      high = Math.max(high, Number(g[i].high));
      low = Math.min(low, Number(g[i].low));
    }
    return {
      date: g[g.length - 1].date,
      open: Number(g[0].open),
      high,
      low,
      close: Number(g[g.length - 1].close),
    };
  });
}
