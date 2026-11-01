import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Sparkles } from "lucide-react";
import { api } from "../api";
import { AiCard, type AiCardData } from "../components/AiCard";
import { Disclaimer, ErrorState, PageHeader, Tag } from "../components";
import { fmtPct } from "../lib";

type Stock = any;

function cell(stock: Stock, key: string) {
  const q = stock?.quote || {};
  const v = stock?.valuation || {};
  const t = stock?.technical || {};
  const r = stock?.report || {};
  const map: Record<string, any> = {
    price: q.price,
    changePct: q.changePct,
    pe: v.pe,
    pb: v.pb,
    pePercentile: v.pePercentile,
    dividendYield: q.dividendYield,
    return20: t.return20,
    drawdown: t.drawdown,
    revenue: r.revenue,
    netProfit: r.netProfit,
    grossMargin: r.grossMargin,
    roe: r.roe,
  };
  return map[key];
}

const ROWS: Array<{ key: string; label: string; fmt?: (v: any) => string }> = [
  { key: "price", label: "收盘价" },
  { key: "changePct", label: "当日涨跌", fmt: (v) => fmtPct(v) },
  { key: "pe", label: "PE(TTM)" },
  { key: "pb", label: "PB" },
  { key: "pePercentile", label: "PE 分位", fmt: (v) => (v == null ? "—" : `${Number(v).toFixed(0)}%`) },
  { key: "dividendYield", label: "股息率" },
  { key: "return20", label: "近 20 日", fmt: (v) => fmtPct(v) },
  { key: "drawdown", label: "阶段回撤", fmt: (v) => fmtPct(v) },
  { key: "revenue", label: "营收(亿)" },
  { key: "netProfit", label: "净利(亿)" },
  { key: "grossMargin", label: "毛利率", fmt: (v) => (v == null ? "—" : `${Number(v).toFixed(1)}%`) },
  { key: "roe", label: "ROE", fmt: (v) => (v == null ? "—" : `${Number(v).toFixed(1)}%`) },
];

export default function Compare() {
  const nav = useNavigate();
  const { a = "", b = "" } = useParams();
  const [sa, setSa] = useState<Stock | null>(null);
  const [sb, setSb] = useState<Stock | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ai, setAi] = useState<AiCardData | null>(null);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [results, setResults] = useState<any[]>([]);

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

  const runAi = async () => {
    setBusy(true);
    setError(null);
    try {
      const data = await api<any>("/api/invest/ai/compare", {
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

  return (
    <div className="page">
      <PageHeader title="多标的对比" sub="同口径差异，不判断谁更好" back onBack={() => nav(-1)} />
      {error ? <ErrorState message={error} onRetry={() => setError(null)} /> : null}
      {!b ? (
        <section className="card">
          <div className="card-title-row"><h2>选择第二个标的</h2><span className="hint">{a}</span></div>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="输入代码或名称"
            style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid var(--line)", fontSize: 13 }}
          />
          <div className="post-list">
            {results.map((it: any) => (
              <button key={it.code} type="button" className="post-row" style={{ textAlign: "left" }} onClick={() => nav(`/compare/${a}/${it.code}`)}>
                <div className="post-row-title">{it.name}</div>
                <div className="hint">{it.code} · {it.industry || "—"}</div>
              </button>
            ))}
          </div>
          {!results.length ? <p className="hint">搜索后选择要对比的标的。</p> : null}
        </section>
      ) : null}
      {sa && sb ? (
        <>
          <div className="card compare-head">
            <div>
              <b>{sa.quote?.name || a}</b>
              <span className="hint">{sa.quote?.code} · {sa.quote?.industry || "—"}</span>
            </div>
            <Tag tone="gray">vs</Tag>
            <div>
              <b>{sb.quote?.name || b}</b>
              <span className="hint">{sb.quote?.code} · {sb.quote?.industry || "—"}</span>
            </div>
          </div>
          <div className="card">
            <table className="data-table">
              <thead>
                <tr><th>指标</th><th>{sa.quote?.name}</th><th>{sb.quote?.name}</th></tr>
              </thead>
              <tbody>
                {ROWS.map((row) => (
                  <tr key={row.key}>
                    <td>{row.label}</td>
                    {[sa, sb].map((s, i) => {
                      const v = cell(s, row.key);
                      return <td key={i}>{v == null ? "待补充" : row.fmt ? row.fmt(v) : String(v)}</td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="hint">数据缺失时显示“待补充”；对比不构成投资建议。</p>
          </div>
          <button className="btn btn-primary btn-sm" onClick={() => void runAi()} disabled={busy}>
            <Sparkles size={15} /> {busy ? "生成中…" : "生成 AI 对比解读"}
          </button>
          {ai ? <AiCard data={ai} /> : null}
        </>
      ) : null}
      <Disclaimer>AI 生成内容仅作研究辅助，不构成投资建议。</Disclaimer>
      <button className="btn btn-ghost btn-sm" onClick={() => nav(-1)}><ArrowLeft size={14} /> 返回</button>
    </div>
  );
}
