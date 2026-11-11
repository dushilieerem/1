import { useLocale } from "../i18n";

type Point = { date?: string; value?: number | null };

export default function FundFlowChart({ points }: { points: Point[] }) {
  const { t } = useLocale();
  const rows = points.slice(-20);
  const values = rows.map((p) => Number(p.value) || 0);
  const maxAbs = Math.max(0.01, ...values.map((v) => Math.abs(v)));
  const w = 340;
  const h = 132;
  const left = 30;
  const right = 8;
  const top = 14;
  const bottom = 24;
  const plotW = w - left - right;
  const plotH = h - top - bottom;
  const zeroY = top + plotH / 2;
  const step = plotW / Math.max(1, rows.length);
  const barW = Math.max(3, Math.min(12, step * 0.55));
  const labelEvery = Math.max(1, Math.ceil(rows.length / 5));

  if (!rows.length) return <div className="empty-inline">{t("暂无资金流数据", "No fund-flow data")}</div>;

  return (
    <svg className="fund-flow-svg" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={t("近 20 日主力资金流向", "20-day main fund flow")}>
      {[maxAbs, 0, -maxAbs].map((tick, i) => {
        const y = zeroY - (tick / maxAbs) * (plotH / 2);
        return (
          <g key={i}>
            <line x1={left} y1={y} x2={w - right} y2={y} stroke={tick === 0 ? "#d7d7d7" : "#f0f0f0"} strokeWidth={tick === 0 ? 1 : 0.8} />
            <text x={left - 4} y={y + 3} textAnchor="end" fontSize="7.5" fill="#999">{tick === 0 ? "0" : `${tick.toFixed(1)}亿`}</text>
          </g>
        );
      })}
      {rows.map((point, i) => {
        const value = Number(point.value) || 0;
        const height = Math.max(1, (Math.abs(value) / maxAbs) * (plotH / 2));
        const x = left + i * step + (step - barW) / 2;
        const y = value >= 0 ? zeroY - height : zeroY;
        return (
          <g key={`${point.date || i}-${i}`}>
            <rect x={x} y={y} width={barW} height={height} rx="1" fill={value >= 0 ? "#e54d42" : "#16a34a"} fillOpacity=".72" />
            {(i % labelEvery === 0 || i === rows.length - 1) && point.date ? (
              <text x={x + barW / 2} y={h - 7} textAnchor="middle" fontSize="7.5" fill="#999">{String(point.date).slice(5)}</text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}
