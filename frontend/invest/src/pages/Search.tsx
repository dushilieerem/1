import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Search as SearchIcon, X } from "lucide-react";
import { api } from "../api";
import { EmptyState, ErrorState, PageHeader, SectionHead, Tag } from "../components";
import { fmtPct, formatPrice } from "../lib";
import { useToast } from "../toast";

export default function Search() {
  const nav = useNavigate();
  const toast = useToast();
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
      api<any>(`/api/invest/search?q=${encodeURIComponent(q)}`)
        .then(setData)
        .catch((e) => setError(e.message));
    }, 220);
    return () => window.clearTimeout(t);
  }, [q]);

  const add = async (code: string) => {
    setBusy(true);
    try {
      await api("/api/invest/watchlist", { method: "POST", body: JSON.stringify({ code }) });
      toast("已加入自选");
    } catch (e: any) {
      toast(e.message || "操作失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <PageHeader title="搜索" sub="股票 / 行业 / 主题 / 预设条件" />
      <div className="search-input">
        <SearchIcon size={18} />
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="输入名称、代码、拼音，如 宁德 / 300750"
          aria-label="搜索股票、行业或主题"
        />
        {q ? <button className="clear-btn" onClick={() => setQ("")} aria-label="清空"><X size={16} /></button> : null}
      </div>

      {q ? (
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
          {condBusy ? "AI 解析中…" : "AI 解析选股条件"}
        </button>
      ) : null}
      {condError ? <div className="hint">{condError}</div> : null}
      {cond && !condError ? (
        <section className="card">
          <div className="card-title-row"><h2>AI 理解的条件</h2><span className="hint">仅解析 · 未执行筛选</span></div>
          {cond.explain ? <p className="review-summary">{cond.explain}</p> : null}
          {Array.isArray(cond.conditions) && cond.conditions.length ? (
            <ul className="fact-list">
              {cond.conditions.map((c: any, i: number) => (
                <li key={i}>{typeof c === "string" ? c : JSON.stringify(c)}</li>
              ))}
            </ul>
          ) : (
            <div className="empty-inline">没有解析出可执行条件；可以补充行业、估值、增速或波动等关键词。</div>
          )}
          <p className="hint">AI 生成 · 非投资建议 · 条件选股结果仅供研究。</p>
        </section>
      ) : null}

      {error ? <ErrorState message={error} /> : null}

      {!q && data ? (
        <>
          <SectionHead title="预设条件" sub="基于收盘快照 · 仅供研究" />
          <div className="stack">
            {data.presets.map((p: any) => (
              <section className="card" key={p.key}>
                <div className="card-title-row"><h2>{p.label}</h2><span className="hint">{p.desc}</span></div>
                {p.items.length === 0 ? <div className="empty-inline">今日无符合项。</div> : p.items.map((s: any) => (
                  <button className="search-result" key={s.code} onClick={() => nav(`/stock/${s.code}`)}>
                    <div><b>{s.name}</b><span>{s.code} · {s.industry}</span></div>
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
          <SectionHead title="搜索结果" sub={`${data.results.length} 条`} />
          {data.results.length === 0 ? (
            <EmptyState title="没有找到" detail="试试股票代码、简称或行业关键词。" />
          ) : (
            <div className="card list-card">
              {data.results.map((r: any) => (
                <div className="search-result-row" key={`${r.type}-${r.id}`}>
                  <button className="search-result-main" onClick={() => nav(r.type === "stock" ? `/stock/${r.id}` : `/topic/${r.id}`)}>
                    <div><b>{r.name}</b><span>{r.sub}</span></div>
                    {r.type === "stock" ? (
                      <div className="search-price"><b>{formatPrice(r.price)}</b><em className={r.changePct >= 0 ? "up" : "down"}>{fmtPct(r.changePct)}</em></div>
                    ) : <Tag tone="red">主题</Tag>}
                  </button>
                  {r.type === "stock" ? (
                    <button className="icon-add" onClick={() => add(r.id)} disabled={busy} aria-label="加入自选"><Plus size={16} /></button>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </>
      ) : null}

      {!data && !error ? <div className="hint">输入关键词开始搜索。</div> : null}
    </div>
  );
}
