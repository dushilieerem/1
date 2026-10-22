import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import {
  axisCategory,
  axisValuePlain,
  darkTooltip,
  legendBase,
} from "@/components/chartTheme";
import type { PaperEquityPoint } from "@/lib/paperTradingApi";

type Props = {
  equity: PaperEquityPoint[];
  height?: number;
};

function fmtMoney(value: number) {
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
}

/** 模拟盘资金曲线：总权益 / 现金 / 持仓市值。 */
export function PaperEquityChart({ equity, height = 320 }: Props) {
  const option = useMemo(() => {
    const dates = equity.map((point) => point.date);
    const total = equity.map((point) => point.totalEquity);
    const cash = equity.map((point) => point.cash);
    const positions = equity.map((point) => point.positionsValue);
    return {
      animation: false,
      tooltip: {
        ...darkTooltip(),
        valueFormatter: (value: number) => `¥${fmtMoney(value)}`,
      },
      legend: {
        ...legendBase(),
        data: ["总权益", "现金", "持仓市值"],
        top: 0,
        right: 8,
      },
      grid: { left: 64, right: 20, top: 36, bottom: 28 },
      xAxis: { ...axisCategory(), data: dates },
      yAxis: {
        ...axisValuePlain(),
        axisLabel: {
          ...axisValuePlain().axisLabel,
          formatter: (value: number) => `${Math.round(value / 10000)}万`,
        },
      },
      series: [
        {
          name: "总权益",
          type: "line",
          data: total,
          showSymbol: false,
          smooth: false,
          lineStyle: { width: 2, color: "#ef4444" },
          itemStyle: { color: "#ef4444" },
        },
        {
          name: "现金",
          type: "line",
          data: cash,
          showSymbol: false,
          lineStyle: { width: 1.2, color: "#38bdf8" },
          itemStyle: { color: "#38bdf8" },
        },
        {
          name: "持仓市值",
          type: "line",
          data: positions,
          showSymbol: false,
          lineStyle: { width: 1.2, color: "#f59e0b" },
          itemStyle: { color: "#f59e0b" },
        },
      ],
    };
  }, [equity]);

  if (!equity.length) {
    return (
      <div className="flex h-[220px] items-center justify-center text-sm text-slate-500">
        暂无净值数据，完成一次结算后显示
      </div>
    );
  }

  return (
    <ReactECharts
      option={option}
      style={{ height }}
      notMerge
      opts={{ renderer: "canvas" }}
    />
  );
}
