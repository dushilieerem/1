import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import { instApi } from "@/lib/instApi";
import { useInstLocale } from "@/components/institution/instLocale";
import { Card, DataFreshness, Empty, Loading } from "./instUi";

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
  items: Bar[];
};

/** 研究页 K 线：复用机构行情接口，日线未复权。 */
export function InstKlineCard({ companyId, symbol }: { companyId: number; symbol: string }) {
  const { t } = useInstLocale();
  const [bars, setBars] = useState<Bar[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    instApi<BarsResponse>(`/companies/${companyId}/bars?limit=120`)
      .then((data) => {
        if (alive) setBars(data.items || []);
      })
      .catch((e: Error) => {
        if (alive) setError(e.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [companyId]);

  const latest = bars[bars.length - 1]?.trade_date;
  const option = useMemo(() => {
    const dates = bars.map((b) => b.trade_date);
    const values = bars.map((b) => [b.open, b.close, b.low, b.high]);
    const volumes = bars.map((b, i) => ({
      value: b.volume ?? 0,
      itemStyle: { color: b.close >= b.open ? "#d9536f" : "#3a9b7a" },
    }));
    return {
      animation: false,
      grid: [
        { left: 44, right: 12, top: 16, height: 170 },
        { left: 44, right: 12, top: 200, height: 42 },
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
          data: values,
          itemStyle: { color: "#d9536f", color0: "#3a9b7a", borderColor: "#d9536f", borderColor0: "#3a9b7a" },
        },
        {
          type: "bar",
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: volumes,
          barMaxWidth: 6,
        },
      ],
    };
  }, [bars]);

  return (
    <Card
      title={t("K 线（日线）", "K-line (daily)")}
      desc={t(`${symbol} · 未复权日线，最近 120 个交易日；只做行情参考。`, `${symbol} · unadjusted daily bars, latest 120 trading days; price reference only.`)}
      actions={<DataFreshness date={latest} label={t("行情", "Market")} />}
    >
      {loading ? <Loading label={t("正在加载行情…", "Loading prices…")} /> : null}
      {!loading && error ? <Empty>{t("暂无 K 线数据。", "No K-line data.")}</Empty> : null}
      {!loading && !error && !bars.length ? <Empty>{t("暂无 K 线数据。", "No K-line data.")}</Empty> : null}
      {!loading && !error && bars.length ? (
        <ReactECharts option={option} style={{ height: 250, width: "100%" }} notMerge lazyUpdate />
      ) : null}
    </Card>
  );
}
