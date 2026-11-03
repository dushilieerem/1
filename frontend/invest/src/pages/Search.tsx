import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Search as SearchIcon, X } from "lucide-react";
import { api } from "../api";
import { EmptyState, ErrorState, PageHeader, SectionHead, Tag } from "../components";
import { fmtPct, formatPrice } from "../lib";
import { useToast } from "../toast";
import { useLocale, withMarket } from "../i18n";

export default function Search() {
  const nav = useNavigate();
  const toast = useToast();
  const { t, market } = useLocale();
  const [q, setQ] = useState("");
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [cond, setCond] = useState<any>(null);
  const [condBusy, setCondBusy] = useState(false);
  const [condError, setCondError] = useState<string | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => {
      setError(null);
      api<any>(withMarket(`/api/invest/search?q=${encodeURIComponent(q)}`, market))
        .then(setData)
        .catch((e) => setError(e.message));
    }, 220);
    return () => window.clearTimeout(t);
  }, [q, market]);

  const add = async (code: string) => {
    setBusy(true);
    try {
      await api(withMarket("/api/invest/watchlist", market), { method: "POST", body: JSON.stringify({ code }) });
      toast(t("已加入自选", "Added to watchlist"));
    } catch (e: any) {
      toast(e.message || t("操作失败", "Action failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <PageHeader
        title={t("搜索", "Search")}
        sub={market === "US" ? t("美股代码 / 名称", "US ticker / name") : t("股票 / 行业 / 主题 / 预设条件", "Stocks / sectors / themes / presets")}
      />
      <div className="search-input">
        <SearchIcon size={18} />
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={market === "US" ? t("输入美股代码或名称，如 AAPL", "Enter a US ticker or name, e.g. AAPL") : t("输入名称、代码、拼音，如 宁德 / 300750", "Name, code or pinyin, e.g. CATL / 300750")}
          aria-label={t("搜索股票、行业或主题", "Search stocks, sectors or themes")}
        />
        {q ? <button className="clear-btn" onClick={() => setQ("")} aria-label={t("清空", "Clear")}><X size={16} /></button> : null}
      </div>

      {q && market === "CN" ? (
        <button
          className="btn btn-ghost btn-sm"
          disabled={condBusy}
          onClick={() => {
            setCondBusy(true);
            setCondError(null);
            api<any>("/api/invest/ai/condition", {
              method: "POST",
              body: JSON.stringify({ query: q }),
            })
              .then((res) => setCond(res.card || null))
              .catch((e: Error) => setCondError(e.message))
              .finally(() => setCondBusy(false));
          }}
        >
          {condBusy ? t("AI 解析中…", "Parsing…") : t("AI 解析选股条件", "Parse screening conditions with AI")}
        </button>
      ) : null}
      {condError ? <div className="hint">{condError}</div> : null}
      {cond && !condError ? (
        <section className="card">
          <div className="card-title-row"><h2>{t("AI 理解的条件", "Conditions parsed by AI")}</h2><span className="hint">{t("仅解析 · 未执行筛选", "Parsed only · not executed")}</span></div>
          {cond.explain ? <p className="review-summary">{cond.explain}</p> : null}
          {Array.isArray(cond.conditions) && cond.conditions.length ? (
            <ul className="fact-list">
              {cond.conditions.map((c: any, i: number) => (
                <li key={i}>{typeof c === "string" ? c : JSON.stringify(c)}</li>
              ))}
            </ul>
          ) : (
            <div className="empty-inline">{t("没有解析出可执行条件；可以补充行业、估值、增速或波动等关键词。", "No executable conditions found. Add sector, valuation, growth or volatility keywords.")}</div>
          )}
          <p className="hint">{t("AI 生成 · 非投资建议 · 条件选股结果仅供研究。", "AI generated · not investment advice · screening output is for research only.")}</p>
        </section>
      ) : null}

      {error ? <ErrorState message={error} /> : null}

      {!q && data ? (
        <>
          <SectionHead title={t("预设条件", "Presets")} sub={t("基于收盘快照 · 仅供研究", "Based on the EOD snapshot · research only")} />
          <div className="stack">
            {data.presets.map((p: any, pi: number) => (
              <section className="card" key={p.key || pi}>
                <div className="card-title-row"><h2>{p.label}</h2><span className="hint">{p.desc}</span></div>
                {p.items.length === 0 ? <div className="empty-inline">{t("今日无符合项。", "No matches today.")}</div> : p.items.map((s: any, si: number) => (
                  <button className="search-result" key={`${s.code}-${si}`} onClick={() => nav(`/stock/${s.code}`)}>
                    <div><b>{s.name}</b><span>{s.sub || s.code}</span></div>
                    <div className="search-price"><b>{formatPrice(s.price)}</b><em className={s.changePct >= 0 ? "up" : "down"}>{fmtPct(s.changePct)}</em></div>
                    <Tag tone="gray">{s.reason}</Tag>
                  </button>
                ))}
              </section>
            ))}
          </div>
        </>
      ) : null}

      {q && data ? (
        <>
          <SectionHead title={t("搜索结果", "Results")} sub={t(`${data.results.length} 条`, `${data.results.length} result(s)`)} />
          {data.results.length === 0 ? (
            <EmptyState title={t("没有找到", "Nothing found")} detail={market === "US" ? t("试试美股代码，如 AAPL。", "Try a US ticker, e.g. AAPL.") : t("试试股票代码、简称或行业关键词。", "Try a ticker, short name or sector keyword.")} />
          ) : (
            <div className="card list-card">
              {data.results.map((r: any) => (
                <div className="search-result-row" key={`${r.type}-${r.id}`}>
                  <button className="search-result-main" onClick={() => nav(r.type === "stock" ? `/stock/${r.id}` : `/topic/${r.id}`)}>
                    <div><b>{r.name}</b><span>{r.sub}</span></div>
                    {r.type === "stock" ? (
                      <div className="search-price"><b>{formatPrice(r.price)}</b><em className={r.changePct >= 0 ? "up" : "down"}>{fmtPct(r.changePct)}</em></div>
                    ) : <Tag tone="red">{t("主题", "Theme")}</Tag>}
                  </button>
                  {r.type === "stock" ? (
                    <button className="icon-add" onClick={() => add(r.id)} disabled={busy} aria-label={t("加入自选", "Add to watchlist")}><Plus size={16} /></button>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </>
      ) : null}

      {!data && !error ? <div className="hint">{t("输入关键词开始搜索。", "Type a keyword to start.")}</div> : null}
    </div>
  );
}
