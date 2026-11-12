import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useLocale } from "../i18n";

export type TrendItem = {
  year: number;
  report_type: "annual" | "h1" | "q1" | "q3";
  label: string;
  report_date: string;
  revenue?: number | null;
  net_profit?: number | null;
  deducted_net_profit?: number | null;
  eps?: number | null;
  gross_margin?: number | null;
  net_margin?: number | null;
  roe?: number | null;
  operating_cf?: number | null;
  revenue_yoy?: number | null;
  profit_yoy?: number | null;
  eps_yoy?: number | null;
  operating_cf_yoy?: number | null;
  deducted_net_profit_yoy?: number | null;
};

const REPORT_TYPES = [
  { key: "annual", zh: "年报", en: "Annual" },
  { key: "h1", zh: "中报", en: "H1" },
  { key: "q1", zh: "一季报", en: "Q1" },
  { key: "q3", zh: "三季报", en: "Q3" },
] as const;

type ReportType = (typeof REPORT_TYPES)[number]["key"];

const METRICS = [
  { key: "revenue", field: "revenue", yoy: "revenue_yoy", unit: "亿元", unit_en: "CNY 100m", zh: "营业收入", en: "Revenue" },
  { key: "net_profit", field: "net_profit", yoy: "profit_yoy", unit: "亿元", unit_en: "CNY 100m", zh: "归母净利", en: "Net profit" },
  { key: "deducted_net_profit", field: "deducted_net_profit", yoy: "deducted_net_profit_yoy", unit: "亿元", unit_en: "CNY 100m", zh: "扣非净利", en: "Deducted net profit" },
  { key: "eps", field: "eps", yoy: "eps_yoy", unit: "元", unit_en: "CNY", zh: "每股收益", en: "EPS" },
  { key: "gross_margin", field: "gross_margin", yoy: null, unit: "%", unit_en: "%", zh: "毛利率", en: "Gross margin" },
  { key: "net_margin", field: "net_margin", yoy: null, unit: "%", unit_en: "%", zh: "净利率", en: "Net margin" },
  { key: "roe", field: "roe", yoy: null, unit: "%", unit_en: "%", zh: "ROE", en: "ROE" },
  { key: "operating_cf", field: "operating_cf", yoy: "operating_cf_yoy", unit: "亿元", unit_en: "CNY 100m", zh: "经营现金流", en: "Operating cash flow" },
] as const;

type Metric = (typeof METRICS)[number];

function finite(value: unknown): number | null {
  const n = Number(value);
  return value === null || value === undefined || !Number.isFinite(n) ? null : n;
}

function fmtValue(metric: Metric, value: number | null, locale: "zh" | "en") {
  if (value === null) return "—";
  if (metric.key === "eps") return value.toFixed(2);
  if (metric.unit === "%") return `${value.toFixed(1)}%`;
  const rounded = Math.round(value * 10) / 10;
  return locale === "en" ? `${rounded.toLocaleString("en-US")} ${metric.unit_en}` : `${rounded.toLocaleString("zh-CN")} ${metric.unit}`;
}

function fmtAxis(metric: Metric, value: number) {
  if (metric.unit === "%") return `${Math.round(value)}%`;
  if (metric.key === "eps") return value.toFixed(2);
  return `${Math.round(value).toLocaleString("zh-CN")}`;
}

function fmtYoy(value: number | null) {
  return value === null ? "—" : `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function QuoteTrendChart({
  rows,
  metric,
  locale,
}: {
  rows: TrendItem[];
  metric: Metric;
  locale: "zh" | "en";
}) {
  const { t } = useLocale();
  const values = rows.map((row) => finite(row[metric.field as keyof TrendItem]));
  const yoys = metric.yoy ? rows.map((row) => finite(row[metric.yoy as keyof TrendItem])) : [];
  const finiteValues = values.filter((x): x is number => x !== null);
  if (!finiteValues.length) {
    return <div className="empty-inline">{t("该指标暂无数据", "No data for this metric")}</div>;
  }
  const w = 340;
  const h = 196;
  const left = 34;
  const right = 10;
  const top = 24;
  const bottom = 26;
  const plotW = w - left - right;
  const plotH = h - top - bottom;
  const minValue = Math.min(0, ...finiteValues);
  const maxValue = Math.max(0, ...finiteValues);
  const valueSpan = maxValue - minValue || 1;
  const yValue = (value: number) => top + plotH - ((value - minValue) / valueSpan) * plotH;
  const zeroY = yValue(0);
  const step = plotW / Math.max(1, rows.length);
  const barW = Math.min(30, step * 0.45);

  const yoyValues = yoys.filter((x): x is number => x !== null);
  const yoyMin = yoyValues.length ? Math.min(...yoyValues) : 0;
  const yoyMax = yoyValues.length ? Math.max(...yoyValues) : 0;
  const yoySpan = yoyMax - yoyMin || 1;
  const yoyY = (value: number) => top + 6 + (1 - (value - yoyMin) / yoySpan) * (plotH - 20);
  const ticks = [0, 1, 2, 3].map((i) => minValue + (valueSpan * i) / 3);

  return (
    <svg className="fin-trend-svg" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={t("财务指标趋势图", "Financial trend chart")}>
      {ticks.map((tick, i) => (
        <g key={i}>
          <line x1={left} y1={yValue(tick)} x2={w - right} y2={yValue(tick)} stroke="#ececec" strokeWidth="1" />
          <text x={left - 5} y={yValue(tick) + 3} textAnchor="end" fontSize="8" fill="#999">{fmtAxis(metric, tick)}</text>
        </g>
      ))}
      <text x={left} y={11} fontSize="8" fill="#999">{locale === "en" ? metric.unit_en : metric.unit}</text>
      {rows.map((row, i) => {
        const value = values[i];
        const x = left + i * step + (step - barW) / 2;
        const barTop = value === null ? zeroY : yValue(value);
        const barY = Math.min(barTop, zeroY);
        const barH = Math.max(1, Math.abs(zeroY - barTop));
        return (
          <g key={`${row.label}-${i}`}>
            {value !== null ? <rect x={x} y={barY} width={barW} height={barH} rx="2" fill="#2f80ed" /> : null}
            {value !== null ? (
              <text x={x + barW / 2} y={barY - 4} textAnchor="middle" fontSize="8.5" fill="#2f80ed">
                {fmtAxis(metric, value)}
              </text>
            ) : null}
            <text x={left + i * step + step / 2} y={h - 7} textAnchor="middle" fontSize="8" fill="#999">{row.label}</text>
          </g>
        );
      })}
      {metric.yoy && yoyValues.length ? (
        <>
          <polyline
            points={rows.map((row, i) => {
              const value = finite(row[metric.yoy as keyof TrendItem]);
              if (value === null) return "";
              return `${left + i * step + step / 2},${yoyY(value)}`;
            }).filter(Boolean).join(" ")}
            fill="none"
            stroke="#f2994a"
            strokeWidth="2.5"
            strokeLinejoin="round"
          />
          {rows.map((row, i) => {
            const value = finite(row[metric.yoy as keyof TrendItem]);
            if (value === null) return null;
            const cx = left + i * step + step / 2;
            const cy = yoyY(value);
            return (
              <g key={`yoy-${i}`}>
                <circle cx={cx} cy={cy} r="2.5" fill="#f2994a" />
                <text x={cx} y={cy - 6} textAnchor="middle" fontSize="8" fill="#f2994a">{fmtYoy(value)}</text>
              </g>
            );
          })}
        </>
      ) : null}
    </svg>
  );
}

export default function FinancialTrend({ items }: { items: TrendItem[] }) {
  const { t, locale } = useLocale();
  const [metricKey, setMetricKey] = useState<(typeof METRICS)[number]["key"]>("revenue");
  const [periodOpen, setPeriodOpen] = useState(false);
  const selectRef = useRef<HTMLDivElement | null>(null);
  const availableTypes = useMemo(
    () => REPORT_TYPES.filter((type) => items.some((item) => item.report_type === type.key)),
    [items],
  );
  const [reportType, setReportType] = useState<ReportType>(() => {
    const preferred = availableTypes.find((x) => x.key === "q3") || availableTypes[availableTypes.length - 1];
    return (preferred?.key || "q3") as ReportType;
  });

  useEffect(() => {
    if (!availableTypes.some((x) => x.key === reportType)) {
      setReportType((availableTypes[availableTypes.length - 1]?.key || "q3") as ReportType);
    }
  }, [availableTypes, reportType]);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (selectRef.current && !selectRef.current.contains(event.target as Node)) setPeriodOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const rows = useMemo(
    () => items.filter((item) => item.report_type === reportType).sort((a, b) => a.year - b.year).slice(-4),
    [items, reportType],
  );
  const metric = METRICS.find((x) => x.key === metricKey) || METRICS[0];
  const latest = rows[rows.length - 1];
  const latestValue = latest ? finite(latest[metric.field as keyof TrendItem]) : null;
  const latestYoy = latest && metric.yoy ? finite(latest[metric.yoy as keyof TrendItem]) : null;
  const currentType = REPORT_TYPES.find((x) => x.key === reportType) || REPORT_TYPES[3];

  let summary = "";
  if (latest && latestValue !== null) {
    summary = `${latest.label} ${locale === "en" ? metric.en : metric.zh} ${fmtValue(metric, latestValue, locale)}`;
    if (latestYoy !== null) summary += `${locale === "en" ? ", " : "，同比 "}${fmtYoy(latestYoy)}`;
    summary += "。";
    if (metric.key === "revenue" && reportType === "q3") {
      const h1 = items.find((x) => x.report_type === "h1" && x.year === latest.year);
      const h1Value = h1 ? finite(h1.revenue) : null;
      if (h1Value !== null && latestValue > h1Value) {
        summary += locale === "en"
          ? ` Q3 single quarter ${fmtValue(metric, latestValue - h1Value, locale)}.`
          : `单季 Q3 ${fmtValue(metric, latestValue - h1Value, locale)}。`;
      }
    }
  }

  if (!items.length) return <div className="empty-inline">{t("暂无财报", "No financials")}</div>;

  return (
    <div className="fin-trend">
      <div className="fin-trend-tabs">
        {METRICS.map((item) => (
          <button
            key={item.key}
            className={metricKey === item.key ? "on" : ""}
            onClick={() => setMetricKey(item.key)}
          >
            {locale === "en" ? item.en : item.zh}
          </button>
        ))}
      </div>
      <div className="fin-trend-legend-row">
        <div className="fin-trend-legend">
          <span><i className="fin-legend-bar" />{t("指标值", "Value")}</span>
          {metric.yoy ? <span><i className="fin-legend-line" />{t("同比增速", "YoY")}</span> : null}
        </div>
        <div className="fin-period-select" ref={selectRef}>
          <button type="button" className={periodOpen ? "on" : ""} onClick={() => setPeriodOpen((v) => !v)}>
            {locale === "en" ? currentType.en : currentType.zh} <ChevronDown size={12} />
          </button>
          {periodOpen ? (
            <div className="fin-period-menu">
              {REPORT_TYPES.map((type) => (
                <button
                  type="button"
                  key={type.key}
                  className={type.key === reportType ? "on" : ""}
                  onClick={() => { setReportType(type.key); setPeriodOpen(false); }}
                >
                  {locale === "en" ? type.en : type.zh}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </div>
      {rows.length ? <QuoteTrendChart rows={rows} metric={metric} locale={locale} /> : <div className="empty-inline">{t("该报告期暂无数据", "No data for this report period")}</div>}
      {summary ? <p className="fin-trend-summary">{summary}</p> : null}
    </div>
  );
}
