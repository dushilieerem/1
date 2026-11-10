import { useLocale } from "../i18n";

export type AiChartData = {
  type?: "bar" | "percentile" | "line" | "kline";
  title?: string;
  title_en?: string;
  labels?: string[];
  values?: Array<number | null>;
  unit?: string;
  source?: string;
  label?: string;
  value?: number | null;
  percentile?: number | null;
};

function BarChart({ chart }: { chart: AiChartData }) {
  const { t } = useLocale();
  const values = chart.values || [];
  const max = Math.max(1, ...values.map((x) => Math.abs(Number(x) || 0)));
  return (
    <div className="ai-chart-box">
      <div className="card-title-row">
        <b>{t(chart.title || "数据图表", chart.title_en || "Data chart")}</b>
        <span className="hint">{chart.source || chart.unit || ""}</span>
      </div>
      <div className="ai-bars" role="img" aria-label={chart.title || "Data chart"}>
        {values.map((value, i) => {
          const n = Number(value) || 0;
          return (
            <i
              key={`${chart.labels?.[i] || i}-${i}`}
              className={n >= 0 ? "in" : "out"}
              style={{ height: `${Math.max(3, (Math.abs(n) / max) * 64)}px` }}
              title={`${chart.labels?.[i] || ""} ${n.toFixed(2)}${chart.unit || ""}`.trim()}
            />
          );
        })}
      </div>
      <div className="ai-bar-labels">
        <span>{chart.labels?.[0] || ""}</span>
        <span>{chart.labels?.[chart.labels.length - 1] || ""}</span>
        <span>{chart.unit || ""}</span>
      </div>
    </div>
  );
}

function PercentileChart({ chart }: { chart: AiChartData }) {
  const { t } = useLocale();
  const pct = chart.percentile == null ? null : Math.max(0, Math.min(100, Number(chart.percentile)));
  return (
    <div className="ai-chart-box">
      <div className="card-title-row">
        <b>{t(chart.title || "估值分位", chart.title_en || "Valuation percentile")}</b>
        <span className="hint">
          {chart.source ? `${chart.source} · ` : ""}
          {chart.value == null ? "—" : `${Number(chart.value).toFixed(2)}${chart.unit || ""}`}
        </span>
      </div>
      <div className="ai-percentile" role="img" aria-label={chart.title || "Percentile"}>
        <i style={{ left: `${pct == null ? 0 : pct}%` }} />
      </div>
      <div className="ai-bar-labels">
        <span>{t("低", "Low")}</span>
        <span>{pct == null ? t("样本不足", "Not enough samples") : `${pct.toFixed(0)}% ${t("分位", "percentile")}`}</span>
        <span>{t("高", "High")}</span>
      </div>
    </div>
  );
}

export default function AiCharts({ charts }: { charts?: AiChartData[] }) {
  if (!charts?.length) return null;
  return (
    <div className="ai-chart-list">
      {charts.map((chart, i) => (
        chart.type === "percentile"
          ? <PercentileChart chart={chart} key={`pct-${i}`} />
          : chart.type === "bar"
            ? <BarChart chart={chart} key={`bar-${i}`} />
            : null
      ))}
    </div>
  );
}

export type PriceTrendData = {
  code?: string;
  bars?: Array<{ date?: string; close?: number }>;
};

export function AiPriceTrend({ chart }: { chart?: PriceTrendData }) {
  const { t } = useLocale();
  const points = (chart?.bars || [])
    .map((b) => ({ date: b.date || "", close: Number(b.close) }))
    .filter((b) => Number.isFinite(b.close));
  if (points.length < 2) return null;
  const values = points.map((p) => p.close);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const w = 340;
  const h = 120;
  const left = 8;
  const right = 8;
  const top = 22;
  const bottom = 22;
  const plotW = w - left - right;
  const plotH = h - top - bottom;
  const x = (i: number) => left + (i / (points.length - 1)) * plotW;
  const y = (v: number) => top + (1 - (v - min) / span) * plotH;
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.close).toFixed(1)}`).join(" ");
  const area = `${line} L${x(points.length - 1).toFixed(1)},${(top + plotH).toFixed(1)} L${x(0).toFixed(1)},${(top + plotH).toFixed(1)} Z`;
  const last = points[points.length - 1];
  return (
    <div className="ai-chart-box ai-price-trend">
      <div className="card-title-row">
        <b>{t(`${chart?.code || ""} 行情走势`, `${chart?.code || ""} price trend`)}</b>
        <span className="hint">{t("近", "Last")} {points.length} {t("个交易日 · 收盘", "trading days · close")}</span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label={t("行情走势图", "Price trend")}>
        <line x1={left} y1={top} x2={w - right} y2={top} stroke="#f0f0f0" strokeWidth="0.8" />
        <line x1={left} y1={top + plotH} x2={w - right} y2={top + plotH} stroke="#f0f0f0" strokeWidth="0.8" />
        <path d={area} fill="rgba(230,0,18,.06)" />
        <path d={line} fill="none" stroke="var(--red)" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={x(points.length - 1)} cy={y(last.close)} r="2.3" fill="var(--red)" />
        <text x={left} y={top - 6} fontSize="8" fill="#999">{max.toFixed(2)}</text>
        <text x={left} y={top + plotH + 12} fontSize="8" fill="#999">{min.toFixed(2)}</text>
        <text x={left} y={h - 4} fontSize="7.5" fill="#999">{points[0].date}</text>
        <text x={w - right} y={h - 4} textAnchor="end" fontSize="7.5" fill="#999">{last.date}</text>
      </svg>
    </div>
  );
}
