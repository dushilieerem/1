import { useLocale } from "../i18n";

type Row = {
  key: string;
  label: string;
  label_en: string;
  fmt: "price" | "pct" | "num" | "x" | "pctile" | string;
  values: Array<number | null>;
  missing: string[];
};

type Dimension = {
  key: string;
  title: string;
  title_en: string;
  rows: Row[];
  missing: Array<{ code: string; name: string; labels: string[] }>;
};

type Highlight = {
  text: string;
  text_en?: string;
  tone?: string;
  source?: string;
};

export type ComparePayload = {
  ok?: boolean;
  items: Array<{ code: string; name: string; industry?: string | null }>;
  dimensions: Dimension[];
  highlights: Array<{ code: string; name: string; positive: Highlight[]; negative: Highlight[] }>;
  summary: Array<{ text: string; text_en?: string }>;
  note?: string;
  note_en?: string;
  disclaimer?: string;
};

const SIGNED = new Set(["changePct", "return5", "revenueYoY", "profitYoY"]);

function fmtValue(row: Row, value: number | null) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
  const n = Number(value);
  if (row.fmt === "price") return n.toFixed(2);
  if (row.fmt === "pct") {
    const sign = SIGNED.has(row.key) && n > 0 ? "+" : "";
    return `${sign}${n.toFixed(row.key === "pePercentile" ? 0 : 1)}%`;
  }
  if (row.fmt === "pctile") return `${n.toFixed(0)}%`;
  if (row.fmt === "x") return `${n.toFixed(2)}x`;
  return n.toFixed(2);
}

function toneClass(row: Row, value: number | null) {
  if (value === null || !SIGNED.has(row.key)) return "";
  return Number(value) > 0 ? "up" : Number(value) < 0 ? "down" : "";
}

export default function CompareView({ data, compact = false }: { data: ComparePayload; compact?: boolean }) {
  const { t, locale } = useLocale();
  const items = data.items || [];
  return (
    <div className={`compare-view ${compact ? "compare-compact" : ""}`}>
      {data.dimensions.map((dim) => (
        <section className="card compare-dim" key={dim.key}>
          <div className="card-title-row">
            <h2>{locale === "en" ? dim.title_en : dim.title}</h2>
            <span className="hint">{t(`${items.length} 只 · 同口径`, `${items.length} names · like-for-like`)}</span>
          </div>
          <div className="compare-scroll">
            <table className="data-table compare-table">
              <thead>
                <tr>
                  <th>{t("指标", "Metric")}</th>
                  {items.map((item) => (
                    <th key={item.code}>
                      <b>{item.name}</b>
                      <small>{item.code}</small>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {dim.rows.map((row) => (
                  <tr key={row.key}>
                    <td>{locale === "en" ? row.label_en : row.label}</td>
                    {row.values.map((value, index) => (
                      <td key={`${row.key}-${index}`} className={toneClass(row, value)}>{fmtValue(row, value)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {dim.missing?.length ? (
            <p className="hint compare-missing">
              {dim.missing.map((m) => t(`${m.name} 缺：${m.labels.join("、")}`, `${m.name} missing: ${m.labels.join(", ")}`)).join("；")}
            </p>
          ) : null}
        </section>
      ))}

      {data.highlights?.length ? (
        <section className="card compare-dim">
          <div className="card-title-row">
            <h2>{t("亮点与风险", "Highlights & risks")}</h2>
            <span className="hint">✓ / ⚠</span>
          </div>
          {data.highlights.map((group) => (
            <div className="compare-hl" key={group.code}>
              <b>{group.name}</b>
              {group.positive.length ? (
                <ul className="compare-hl-list good">
                  {group.positive.map((item, i) => (
                    <li key={`p-${i}`}><span>✓</span>{locale === "en" ? item.text_en || item.text : item.text}</li>
                  ))}
                </ul>
              ) : null}
              {group.negative.length ? (
                <ul className="compare-hl-list warn">
                  {group.negative.map((item, i) => (
                    <li key={`n-${i}`}><span>⚠</span>{locale === "en" ? item.text_en || item.text : item.text}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ))}
          <p className="hint">{locale === "en" ? data.note_en : data.note}</p>
        </section>
      ) : null}

      {data.summary?.length ? (
        <section className="card compare-dim">
          <div className="card-title-row"><h2>{t("总结", "Summary")}</h2></div>
          <ul className="compare-summary">
            {data.summary.map((line, i) => (
              <li key={i}>{locale === "en" ? line.text_en || line.text : line.text}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {data.disclaimer ? <p className="hint">{data.disclaimer}</p> : null}
    </div>
  );
}
