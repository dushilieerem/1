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
