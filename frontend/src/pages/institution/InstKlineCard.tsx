import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import { instApi } from "@/lib/instApi";
import { useInstLocale } from "@/components/institution/instLocale";
import { Badge, Button, Card, DataFreshness, Empty, Loading } from "./instUi";

type Bar = {
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

type BarsResponse = {
  symbol: string;
  name?: string;
  adjust?: string;
  period?: string;
  available?: boolean;
  note?: string;
  items: Bar[];
};

type Period = "min" | "1min" | "5min" | "15min" | "60min" | "day" | "week" | "month";

const PERIODS: Array<{ key: Period; zh: string; en: string }> = [
  { key: "min", zh: "分时", en: "Intraday" },
  { key: "1min", zh: "1 分", en: "1m" },
  { key: "5min", zh: "5 分", en: "5m" },
  { key: "15min", zh: "15 分", en: "15m" },
  { key: "60min", zh: "60 分", en: "60m" },
  { key: "day", zh: "日 K", en: "Daily" },
  { key: "week", zh: "周 K", en: "Weekly" },
  { key: "month", zh: "月 K", en: "Monthly" },
];

const MA_WINDOWS = [5, 10, 20, 60] as const;
const PERIOD_LABEL: Record<string, [string, string]> = {
  min: ["分时", "intraday"],
  "1min": ["1 分钟", "1-minute"],
  "5min": ["5 分钟", "5-minute"],
  "15min": ["15 分钟", "15-minute"],
  "60min": ["60 分钟", "60-minute"],
  day: ["日线", "daily"],
  week: ["周线", "weekly"],
  month: ["月线", "monthly"],
};

function movingAverage(values: number[], window: number): Array<number | null> {
  const out: Array<number | null> = [];
  let sum = 0;
  for (let i = 0; i < values.length; i += 1) {
    sum += values[i];
    if (i >= window) sum -= values[i - window];
    out.push(i >= window - 1 ? Number((sum / window).toFixed(2)) : null);
  }
  return out;
}

/** 行情 K 线：日/周/月可切，分钟线依赖行情源；均线前端计算，30 秒轮询最新日线。 */
export function InstKlineCard({ companyId, symbol }: { companyId: number; symbol: string }) {
  const { t } = useInstLocale();
  const [period, setPeriod] = useState<Period>("day");
  const [enabledMa, setEnabledMa] = useState<Record<number, boolean>>({ 5: true, 10: true, 20: true, 60: false });
  const [bars, setBars] = useState<Bar[]>([]);
  const [available, setAvailable] = useState(true);
  const [note, setNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = (showLoading: boolean) => {
      if (showLoading) setLoading(true);
      setError(null);
      instApi<BarsResponse>(`/companies/${companyId}/bars?limit=120&period=${period}`)
        .then((data) => {
          if (!alive) return;
          setBars(data.items || []);
          setAvailable(data.available !== false);
          setNote(data.note || null);
        })
        .catch((e: Error) => {
          if (alive) setError(e.message);
        })
        .finally(() => {
          if (alive) setLoading(false);
        });
    };
    load(true);
    const timer = window.setInterval(() => load(false), 30_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [companyId, period]);

  const latest = bars[bars.length - 1]?.trade_date;
  const periodLabel = PERIOD_LABEL[period] || PERIOD_LABEL.day;
  const option = useMemo(() => {
    const dates = bars.map((b) => b.trade_date);
    const values = bars.map((b) => [b.open, b.close, b.low, b.high]);
    const closes = bars.map((b) => b.close);
    const volumes = bars.map((b) => ({
      value: b.volume ?? 0,
      itemStyle: { color: b.close >= b.open ? "#d9536f" : "#3a9b7a" },
    }));
    const maSeries = MA_WINDOWS.filter((w) => enabledMa[w]).map((w, idx) => ({
      type: "line",
      name: `MA${w}`,
      data: movingAverage(closes, w),
      smooth: true,
      showSymbol: false,
      lineStyle: { width: 1.2, color: ["#c58a2a", "#3d7bd6", "#8a4fc0", "#3a9b7a"][idx % 4] },
    }));
    return {
      animation: false,
      legend: { top: 0, right: 8, textStyle: { fontSize: 10, color: "#77718c" } },
      grid: [
        { left: 52, right: 12, top: 28, height: 160 },
        { left: 52, right: 12, top: 202, height: 42 },
      ],
      tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
      xAxis: [
        {
          type: "category",
          data: dates,
          boundaryGap: true,
          axisLabel: { color: "#77718c", fontSize: 10 },
          axisLine: { lineStyle: { color: "#e3eaf8" } },
        },
        {
          type: "category",
          gridIndex: 1,
          data: dates,
          axisLabel: { show: false },
          axisLine: { lineStyle: { color: "#e3eaf8" } },
        },
      ],
      yAxis: [
        {
          scale: true,
          splitLine: { lineStyle: { color: "#f1f5f9" } },
          axisLabel: { color: "#77718c", fontSize: 10 },
        },
        {
          gridIndex: 1,
          splitNumber: 2,
          splitLine: { show: false },
          axisLabel: { color: "#a9a4bd", fontSize: 9 },
        },
      ],
      series: [
        {
          type: "candlestick",
          name: t("K 线", "Candles"),
          data: values,
          itemStyle: { color: "#d9536f", color0: "#3a9b7a", borderColor: "#d9536f", borderColor0: "#3a9b7a" },
        },
        ...maSeries,
        {
          type: "bar",
          name: t("成交量", "Volume"),
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: volumes,
          barMaxWidth: 6,
        },
      ],
    };
  }, [bars, enabledMa, t]);

  return (
    <Card
      title={t("K 线（实时行情）", "K-line (live prices)")}
      desc={t(
        `${symbol} · 未复权${periodLabel[0]}数据，最近 120 根；均线可勾选，30 秒刷新一次。只做行情参考。`,
        `${symbol} · unadjusted ${periodLabel[1]} bars, latest 120; selectable moving averages, refreshed every 30s. Price reference only.`,
      )}
      actions={<DataFreshness date={latest} label={t("行情", "Market")} />}
    >
      <div className="mb-3 flex flex-wrap items-center gap-1.5">
        {PERIODS.map((p) => (
          <Button
            key={p.key}
            variant={period === p.key ? "gold" : "ghost"}
            onClick={() => setPeriod(p.key)}
          >
            {t(p.zh, p.en)}
          </Button>
        ))}
        <span className="mx-1 h-4 w-px bg-[#e3eaf8]" />
        {MA_WINDOWS.map((w) => (
          <label key={w} className="flex items-center gap-1 text-[11px] text-[#68738b]">
            <input
              type="checkbox"
              checked={Boolean(enabledMa[w])}
              onChange={(e) => setEnabledMa((prev) => ({ ...prev, [w]: e.target.checked }))}
            />
            MA{w}
          </label>
        ))}
        {!available ? <Badge tone="amber">{t("分钟数据未接入", "Minute data unavailable")}</Badge> : null}
      </div>
      {loading ? <Loading label={t("正在加载行情…", "Loading prices…")} /> : null}
      {!loading && error ? <Empty>{t("暂无 K 线数据。", "No K-line data.")}</Empty> : null}
      {!loading && !error && !bars.length ? (
        <Empty>{note || t("暂无 K 线数据。", "No K-line data.")}</Empty>
      ) : null}
      {!loading && !error && bars.length ? (
        <ReactECharts option={option} style={{ height: 260, width: "100%" }} notMerge lazyUpdate />
      ) : null}
    </Card>
  );
}
