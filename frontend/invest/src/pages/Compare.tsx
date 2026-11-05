import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { api } from "../api";
import { AiCard, type AiCardData } from "../components/AiCard";
import { Disclaimer, ErrorState, PageHeader, Tag } from "../components";
import { displayIndustry, fmtPct, formatPrice } from "../lib";
import { useLocale } from "../i18n";

type Stock = any;

function cell(stock: Stock, key: string) {
  const q = stock?.quote || {};
  const v = stock?.valuation || {};
  const tech = stock?.technical || {};
  const r = stock?.report || {};
  const map: Record<string, any> = {
    price: q.price,
    changePct: q.changePct,
    pe: v.pe,
    pb: v.pb,
    pePercentile: v.pePercentile,
    dividendYield: q.dividendYield,
    return20: tech.return20,
    drawdown: tech.drawdown,
    revenue: r.revenue,
    netProfit: r.netProfit,
    grossMargin: r.grossMargin,
    roe: r.roe,
  };
  return map[key];
}

const ROWS: Array<{ key: string; label: { zh: string; en: string }; fmt?: (v: any) => string }> = [
  { key: "price", label: { zh: "收盘价", en: "Close" }, fmt: (v) => formatPrice(v) },
  { key: "changePct", label: { zh: "当日涨跌", en: "Daily change" }, fmt: (v) => fmtPct(v) },
  { key: "pe", label: { zh: "PE(TTM)", en: "PE (TTM)" }, fmt: (v) => `${Number(v).toFixed(2)}x` },
  { key: "pb", label: { zh: "PB", en: "PB" }, fmt: (v) => `${Number(v).toFixed(2)}x` },
  { key: "pePercentile", label: { zh: "PE 分位", en: "PE percentile" }, fmt: (v) => `${Number(v).toFixed(0)}%` },
  { key: "dividendYield", label: { zh: "股息率", en: "Dividend yield" }, fmt: (v) => `${Number(v).toFixed(2)}%` },
  { key: "return20", label: { zh: "近 20 日", en: "Last 20 days" }, fmt: (v) => fmtPct(v) },
  { key: "drawdown", label: { zh: "阶段回撤", en: "Drawdown" }, fmt: (v) => fmtPct(v) },
  { key: "revenue", label: { zh: "营收（亿元）", en: "Revenue (CNY 100m)" }, fmt: (v) => Number(v).toFixed(2) },
  { key: "netProfit", label: { zh: "净利（亿元）", en: "Net profit (CNY 100m)" }, fmt: (v) => Number(v).toFixed(2) },
  { key: "grossMargin", label: { zh: "毛利率", en: "Gross margin" }, fmt: (v) => (v == null ? "—" : `${Number(v).toFixed(1)}%`) },
  { key: "roe", label: { zh: "ROE", en: "ROE" }, fmt: (v) => (v == null ? "—" : `${Number(v).toFixed(1)}%`) },
];

export default function Compare() {
  const { t } = useLocale();
  const nav = useNavigate();
  const { a = "", b = "" } = useParams();
  const [sa, setSa] = useState<Stock | null>(null);
  const [sb, setSb] = useState<Stock | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ai, setAi] = useState<AiCardData | null>(null);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [results, setResults] = useState<any[]>([]);
  const aiStarted = useRef("");

  useEffect(() => {
    if (b) return;
    const term = q.trim();
    if (!term) {
      setResults([]);
      return;
    }
    const timer = setTimeout(() => {
      api<any>(`/api/invest/search?q=${encodeURIComponent(term)}`)
        .then((d) => setResults(d.items || []))
        .catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [q, b]);

  useEffect(() => {
    if (!b) return;
    Promise.all([api<Stock>(`/api/invest/stock/${a}`), api<Stock>(`/api/invest/stock/${b}`)])
      .then(([x, y]) => {
        setSa(x);
        setSb(y);
      })
      .catch((e) => setError(e.message));
  }, [a, b]);

  const runAi = async (refresh = false) => {
    setBusy(true);
    setError(null);
    try {
      const data = await api<any>(`/api/invest/ai/compare?refresh=${refresh ? 1 : 0}`, {
        method: "POST",
        body: JSON.stringify({ a, b }),
      });
      setAi({ card: data.card, blocked: data.blocked });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!sa || !sb || !a || !b) return;
    const key = `${a}|${b}`;
    if (aiStarted.current === key) return;
    aiStarted.current = key;
    void runAi(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sa, sb, a, b]);

  return (
    <div className="page">
      <PageHeader title={t("多标的对比", "Stock comparison")} sub={t("同口径差异，不判断谁更好", "Like-for-like differences, without picking a winner")} back onBack={() => nav(-1)} />
      {error ? <ErrorState message={error} onRetry={() => setError(null)} /> : null}
      {!b ? (
        <section className="card">
          <div className="card-title-row"><h2>{t("选择第二个标的", "Choose a second stock")}</h2><span className="hint">{a}</span></div>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("输入代码或名称", "Enter a code or name")}
            style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid var(--line)", fontSize: 13 }}
          />
          <div className="post-list">
            {results.map((it: any) => (
              <button key={it.code} type="button" className="post-row" style={{ textAlign: "left" }} onClick={() => nav(`/compare/${a}/${it.code}`)}>
                <div className="post-row-title">{it.name}</div>
                <div className="hint">{it.code} · {it.industry ? displayIndustry(it.industry) : "—"}</div>
              </button>
            ))}
          </div>
          {!results.length ? <p className="hint">{t("搜索后选择要对比的标的。", "Search, then pick a stock to compare.")}</p> : null}
        </section>
      ) : null}
      {sa && sb ? (
        <>
          <div className="card compare-head">
            <div>
              <b>{sa.quote?.name || a}</b>
              <span className="hint">{sa.quote?.code} · {sa.quote?.industry ? displayIndustry(sa.quote.industry) : "—"}</span>
            </div>
            <Tag tone="gray">vs</Tag>
            <div>
              <b>{sb.quote?.name || b}</b>
              <span className="hint">{sb.quote?.code} · {sb.quote?.industry ? displayIndustry(sb.quote.industry) : "—"}</span>
            </div>
          </div>
          <div className="card">
            <table className="data-table">
              <thead>
                <tr><th>{t("指标", "Metric")}</th><th>{sa.quote?.name}</th><th>{sb.quote?.name}</th></tr>
              </thead>
              <tbody>
                {ROWS.map((row) => (
                  <tr key={row.key}>
                    <td>{t(row.label.zh, row.label.en)}</td>
                    {[sa, sb].map((s, i) => {
                      const v = cell(s, row.key);
                      return <td key={i}>{v == null ? "—" : row.fmt ? row.fmt(v) : String(v)}</td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="hint">{t("缺失项显示 —；对比不构成投资建议。", "Missing values show as —; this comparison is not investment advice.")}</p>
          </div>
          <p className="hint">{t("AI 对比结论自动生成 · 50 字以内 · 不满意可重新生成", "AI comparison is generated automatically · 50-character takeaway · regenerate if needed")}</p>
          {busy && !ai ? <div className="ai-loading">{t("AI 正在对比…", "AI is comparing…")}</div> : null}
          {ai ? <AiCard data={ai} onRegenerate={() => void runAi(true)} busy={busy} /> : null}
        </>
      ) : null}
      <Disclaimer>{t("AI 生成内容仅作研究辅助，不构成投资建议。", "AI-generated content is for research support only and is not investment advice.")}</Disclaimer>
      <button className="btn btn-ghost btn-sm" onClick={() => nav(-1)}><ArrowLeft size={14} /> {t("返回", "Back")}</button>
    </div>
  );
}
