import { useMemo } from "react";
import { useLocale } from "../i18n";

type Point = { date?: string; nav?: number; benchmark?: number };

/** 策略/基准双线图：只画净值，不画预测或目标区间。 */
export default function QuantChart({
  points,
  height = 168,
  showLegend = true,
}: {
  points: Point[];
  height?: number;
  showLegend?: boolean;
}) {
  const { t } = useLocale();
  const width = 320;
  const pad = { l: 30, r: 8, t: 12, b: 18 };
  const data = useMemo(
    () =>
      (points || []).filter(
        (p) => typeof p.nav === "number" && Number.isFinite(p.nav),
      ),
    [points],
  );
  if (data.length < 2) {
    return (
      <div className="quant-chart-empty" style={{ height }}>
        <span>{t("净值曲线待补充", "Equity curve pending")}</span>
      </div>
    );
  }
  const navs = data.map((p) => Number(p.nav));
  const benches = data.map((p) => Number(p.benchmark)).filter((n) => Number.isFinite(n));
  const all = [...navs, ...benches];
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || 0.01;
  const x = (i: number) => pad.l + (i / Math.max(1, data.length - 1)) * (width - pad.l - pad.r);
  const y = (v: number) => pad.t + (1 - (v - min) / span) * (height - pad.t - pad.b);
  const navLine = data.map((p, i) => `${x(i).toFixed(1)},${y(Number(p.nav)).toFixed(1)}`).join(" ");
  const benchLine = benches.length === data.length
    ? data.map((p, i) => `${x(i).toFixed(1)},${y(Number(p.benchmark)).toFixed(1)}`).join(" ")
    : "";
  const first = data[0]?.date || "";
  const last = data[data.length - 1]?.date || "";
  return (
    <div className="quant-chart-wrap">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height={height}
        role="img"
        aria-label={t("策略与基准净值曲线", "Strategy and benchmark equity curve")}
      >
        {[0, 0.5, 1].map((p) => (
          <g key={p}>
            <line
              x1={pad.l}
              x2={width - pad.r}
              y1={pad.t + p * (height - pad.t - pad.b)}
              y2={pad.t + p * (height - pad.t - pad.b)}
              stroke="var(--line)"
              strokeDasharray="2 4"
            />
            <text x={2} y={pad.t + p * (height - pad.t - pad.b) + 4} className="quant-axis">
              {(max - p * span).toFixed(2)}
            </text>
          </g>
        ))}
        {benchLine ? (
          <polyline points={benchLine} fill="none" stroke="#8a91a6" strokeWidth="1.5" strokeDasharray="4 3" />
        ) : null}
        <polyline points={navLine} fill="none" stroke="var(--red)" strokeWidth="2.1" strokeLinecap="round" />
        <text x={pad.l} y={height - 3} className="quant-axis">{first}</text>
        <text x={width - pad.r} y={height - 3} textAnchor="end" className="quant-axis">{last}</text>
      </svg>
      {showLegend ? (
        <div className="quant-legend">
          <span><i className="line nav" />{t("策略", "Strategy")}</span>
          <span><i className="line bench" />{t("基准", "Benchmark")}</span>
        </div>
      ) : null}
    </div>
  );
}
