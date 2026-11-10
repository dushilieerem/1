import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, Newspaper, Search } from "lucide-react";
import { InstV3KlineChart } from "@/components/institution/v3/InstV3KlineChart";
import { fmtDateTime } from "@/lib/instApi";
import {
  fetchV3StockBars,
  fetchV3Stocks,
  type V3Bar,
  type V3Stock,
} from "@/lib/instV3Api";
import { listNews, type NewsItem } from "@/lib/newsApi";

const PERIODS = [
  { key: "day", label: "日K" },
  { key: "week", label: "周K" },
  { key: "month", label: "月K" },
] as const;

const POOL_LABEL: Record<string, string> = {
  research: "研究中",
  watch: "自选",
  dropped: "已移出",
};

function fmtPrice(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(2);
}

function fmtVolume(value: number | null | undefined): string {
  const n = Number(value || 0);
  if (!n) return "—";
  if (n >= 1e8) return `${(n / 1e8).toFixed(2)} 亿`;
  if (n >= 1e4) return `${(n / 1e4).toFixed(2)} 万`;
  return String(Math.round(n));
}

export function InstV3StocksPage() {
  const [stocks, setStocks] = useState<V3Stock[]>([]);
  const [stockTotal, setStockTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [stocksLoading, setStocksLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [period, setPeriod] = useState<(typeof PERIODS)[number]["key"]>("day");
  const [bars, setBars] = useState<V3Bar[]>([]);
  const [barsLoading, setBarsLoading] = useState(false);
  const [barsError, setBarsError] = useState<string | null>(null);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [newsLoading, setNewsLoading] = useState(false);
  const [newsError, setNewsError] = useState<string | null>(null);
  const [newsNote, setNewsNote] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const timer = window.setTimeout(() => {
      setStocksLoading(true);
      fetchV3Stocks(q, 200)
        .then((res) => {
          if (!alive) return;
          const items = [...(res.items || [])].sort((a, b) => {
            const rank = { research: 0, watch: 1, dropped: 2 } as Record<string, number>;
            return (rank[String(a.pool_status || "")] ?? 3) - (rank[String(b.pool_status || "")] ?? 3);
          });
          setStocks(items);
          setStockTotal(Number(res.total || items.length));
          setSelectedId((cur) => (items.some((s) => s.id === cur) ? cur : items[0]?.id ?? null));
        })
        .catch((e: Error) => { if (alive) setError(e.message); })
        .finally(() => {
          if (alive) {
            setLoading(false);
            setStocksLoading(false);
          }
        });
    }, q.trim() ? 250 : 0);
    return () => { alive = false; window.clearTimeout(timer); };
  }, [q]);

  const selected = useMemo(
    () => stocks.find((s) => s.id === selectedId) || null,
    [stocks, selectedId],
  );

  useEffect(() => {
    if (!selectedId) {
      setBars([]);
      setBarsError(null);
      return;
    }
    let alive = true;
    setBarsLoading(true);
    setBarsError(null);
    fetchV3StockBars(selectedId, period, period === "day" ? 160 : 120)
      .then((res) => {
        if (!alive) return;
        const items = [...(res.items || [])].sort((a, b) =>
          String(a.trade_date).localeCompare(String(b.trade_date)),
        );
        setBars(items);
        if (res.available === false) setBarsError(res.note || "该周期行情暂不可用");
      })
      .catch((e: Error) => { if (alive) setBarsError(e.message); })
      .finally(() => { if (alive) setBarsLoading(false); });
    return () => { alive = false; };
  }, [selectedId, period]);

  useEffect(() => {
    if (!selected?.symbol) {
      setNews([]);
      setNewsError(null);
      return;
    }
    let alive = true;
    setNewsLoading(true);
    setNewsError(null);
    setNewsNote(null);
    listNews({ symbol: selected.symbol, limit: 12 })
      .then(async (res) => {
        if (!alive) return;
        if (res.items?.length) {
          setNews(res.items);
          return;
        }
        // 新闻源大量未打 symbol 标签；没有精确匹配时按公司名兜底，并明确标注。
        const q = String(selected.name || selected.symbol.split(".")[0] || "").trim();
        if (!q) { setNews([]); return; }
        const fallback = await listNews({ q, limit: 12 });
        if (!alive) return;
        setNews(fallback.items || []);
        setNewsNote(fallback.items?.length ? "资讯未打标，以下按公司名称匹配" : null);
      })
      .catch((e: Error) => { if (alive) setNewsError(e.message); })
      .finally(() => { if (alive) setNewsLoading(false); });
    return () => { alive = false; };
  }, [selected?.symbol, selected?.name]);

  const last = bars.length ? bars[bars.length - 1] : null;
  const prev = bars.length > 1 ? bars[bars.length - 2] : null;
  const change = last && prev && Number(prev.close) ? Number(last.close) / Number(prev.close) - 1 : null;
  const tone = change === null ? "" : change >= 0 ? "up" : "down";

  if (loading) return <div className="v3-loading">正在加载股票总览…</div>;
  if (error) return <div className="v3-card">加载失败：{error}</div>;

  return (
    <>
      <div className="v3-page-head">
        <div>
          <div className="v3-eyebrow">STOCKS</div>
          <h1>股票总览</h1>
          <p>公司池全量标的的 K 线与相关资讯；只读视图，不改变研究或持仓状态。</p>
        </div>
        <span className="v3-chip info">{stockTotal} 只标的</span>
      </div>

      <div className="v3-stock-grid">
        <aside className="v3-card v3-stock-list">
          <div className="v3-stock-search">
            <Search className="h-3.5 w-3.5" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="搜索代码 / 名称 / 行业"
              aria-label="搜索股票"
            />
          </div>
          <div className="v3-stock-note">展示 {stocks.length} / {stockTotal}；搜索可按代码或名称查全量</div>
          <div className="v3-stock-items">
            {stocks.map((s) => (
              <button
                key={s.id}
                type="button"
                className={`v3-stock-item${s.id === selectedId ? " on" : ""}`}
                onClick={() => setSelectedId(s.id)}
              >
                <span className="v3-stock-symbol">{s.symbol}</span>
                <span className="v3-stock-name">{s.name}</span>
                <span className="v3-stock-meta">
                  {s.industry || s.market || "行业待补"} · {POOL_LABEL[String(s.pool_status || "")] || "未入池"}
                </span>
              </button>
            ))}
            {stocksLoading ? <div className="v3-stock-empty" style={{ padding: "12px 8px" }}>正在筛选…</div> : null}
            {!stocksLoading && !stocks.length ? <div className="v3-empty" style={{ padding: "18px 8px" }}>没有匹配的标的。</div> : null}
          </div>
        </aside>

        <div className="v3-stock-main">
          <section className="v3-card">
            <div className="v3-card-head">
              <div>
                <h2>{selected ? `${selected.name} ${selected.symbol}` : "选择一只股票"}</h2>
                <p>{selected?.industry || "行业待补"} · 数据截至最新日线</p>
              </div>
              <div className="v3-stock-periods">
                {PERIODS.map((p) => (
                  <button
                    key={p.key}
                    type="button"
                    className={`v3-stock-period${period === p.key ? " on" : ""}`}
                    onClick={() => setPeriod(p.key)}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            {last ? (
              <div className="v3-stock-quote">
                <b className={tone}>{fmtPrice(last.close)}</b>
                <span className={`v3-stock-chg ${tone}`}>
                  {change === null ? "—" : `${change >= 0 ? "+" : ""}${(change * 100).toFixed(2)}%`}
                </span>
                <span className="v3-stock-stats">
                  高 {fmtPrice(last.high)} · 低 {fmtPrice(last.low)} · 量 {fmtVolume(last.volume)}
                </span>
              </div>
            ) : null}

            {barsLoading ? <div className="v3-loading" style={{ padding: "40px 0" }}>正在加载 K 线…</div> : null}
            {barsError ? <div className="v3-stock-empty">{barsError}</div> : null}
            {!barsLoading && !barsError && bars.length ? <InstV3KlineChart bars={bars} /> : null}
            {!barsLoading && !barsError && !bars.length ? <div className="v3-stock-empty">暂无 K 线数据。</div> : null}
          </section>

          <section className="v3-card">
            <div className="v3-card-head">
              <div><h2><Newspaper className="mr-1 inline h-4 w-4" />相关资讯</h2><p>按标的代码匹配的新闻与研报摘要，打开原文查看全文。{newsNote ? ` · ${newsNote}` : ""}</p></div>
              <span className="v3-chip">{selected?.symbol || "—"}</span>
            </div>
            {newsLoading ? <div className="v3-loading" style={{ padding: "20px 0" }}>正在加载资讯…</div> : null}
            {newsError ? <div className="v3-stock-empty">{newsError}</div> : null}
            {!newsLoading && !newsError ? (
              <div className="v3-stock-news">
                {news.map((n) => (
                  <article key={n.id} className="v3-stock-news-item">
                    <a href={`/news/${n.id}`} target="_blank" rel="noreferrer">
                      {n.title}
                      <ArrowUpRight className="ml-1 inline h-3 w-3" />
                    </a>
                    <p>
                      {n.sourceLabel || n.source} · {fmtDateTime(n.publishedAt)}
                      {n.isFlash ? " · 快讯" : ""}
                    </p>
                    {n.summary ? <span>{n.summary}</span> : null}
                  </article>
                ))}
                {!news.length ? <div className="v3-stock-empty">暂无与 {selected?.symbol || "该标的"} 匹配的资讯。</div> : null}
              </div>
            ) : null}
          </section>
        </div>
      </div>
    </>
  );
}
