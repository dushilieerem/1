import { lazy, Suspense, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ChevronRight,
  FileText,
  Search,
  Share2,
  Star,
} from "lucide-react";
import { api } from "../api";
import { Disclaimer, ErrorState, Kv, LoadingCards, Sheet, Tag } from "../components";
import { displayIndustry, fmtMarketCap, fmtMoney, fmtPct, fmtShares, formatPrice } from "../lib";
import { useToast } from "../toast";
import GlossarySheet from "../GlossarySheet";
import AiPanel from "../components/AiPanel";
import FinancialTrend from "../components/FinancialTrend";
import FundFlowChart from "../components/FundFlowChart";
import { SUB_INDICATORS, formatCompact, kdj, latestValue, macd, movingAverage, rsi, type SubIndicator } from "../chartIndicators";

import { useLocale, withMarket } from "../i18n";

const KLineChart = lazy(() => import("../KLineChart"));
const VolumeChart = lazy(() => import("../VolumeChart"));

const PERIODS = [
  { key: "daily", zh: "日K", en: "D" },
  { key: "weekly", zh: "周K", en: "W" },
  { key: "monthly", zh: "月K", en: "M" },
];

const BOARD_LABEL: Record<string, string> = {
  SH_MAIN: "沪市主板",
  SZ_MAIN: "深市主板",
  ChiNext: "创业板",
  STAR: "科创板",
  BSE: "北交所",
};

const fmtYi = (value: any) => {
  const n = Number(value);
  return Number.isFinite(n) ? `${(n / 1e8).toFixed(1)} 亿` : "—";
};

function FundDistribution({ rows }: { rows: any[] }) {
  const { t } = useLocale();
  const max = Math.max(1, ...rows.map((r) => Math.abs(Number(r.value) || 0)));
  return (
    <div className="fund-dist">
      {rows.map((r) => (
        <div className="fund-dist-row" key={r.key}>
          <span>{t(r.label, r.label_en)}</span>
          <div className="fund-dist-track">
            <i className={Number(r.value) >= 0 ? "in" : "out"} style={{ width: `${Math.max(3, (Math.abs(Number(r.value)) / max) * 100)}%` }} />
          </div>
          <b className={Number(r.value) >= 0 ? "up" : "down"}>{Number(r.value) >= 0 ? "+" : ""}{Number(r.value).toFixed(2)} 亿</b>
        </div>
      ))}
    </div>
  );
}

export default function Stock() {
  const { code } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const { t } = useLocale();
  const isUs = Boolean(code && code.includes("."));
  const market = isUs ? "US" : "CN";
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState("daily");
  const [tab, setTab] = useState("news");
  const [newsOpen, setNewsOpen] = useState(false);
  const [statementOpen, setStatementOpen] = useState(false);
  const [glossary, setGlossary] = useState(false);
  const [inWatch, setInWatch] = useState(false);
  const [watchBusy, setWatchBusy] = useState(false);
  const [indicator, setIndicator] = useState<"ma" | "boll">("ma");
  const [subIndicator, setSubIndicator] = useState<SubIndicator>("volume");
  const [chartRange, setChartRange] = useState<{ from: number; to: number } | null>(null);

  const load = (nextPeriod = period) => {
    setError(null);
    api(`/api/invest/stock/${code}?period=${nextPeriod}`)
      .then(setData)
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    setData(null);
    setPeriod("daily");
    load("daily");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code]);

  useEffect(() => {
    const length = (data?.chart?.bars || []).length;
    if (length) setChartRange({ from: Math.max(0, length - 120), to: length - 1 });
    else setChartRange(null);
  }, [code, period, data?.chart?.bars?.length]);

  useEffect(() => {
    api<any>(withMarket("/api/invest/watchlist", market))
      .then((w) => setInWatch((w.groups || []).some((g: any) => g.items.some((i: any) => i.code === code))))
      .catch(() => {});
  }, [code, market]);

  const changePeriod = (p: string) => {
    if (p === period) return;
    setPeriod(p);
    setChartRange(null);
    load(p);
  };

  const toggleWatch = async () => {
    if (watchBusy) return;
    setWatchBusy(true);
    try {
      if (inWatch) {
        await api(withMarket(`/api/invest/watchlist/${code}`, market), { method: "DELETE" });
        setInWatch(false);
        toast(t("已移出自选", "Removed from watchlist"));
      } else {
        await api(withMarket("/api/invest/watchlist", market), { method: "POST", body: JSON.stringify({ code }) });
        setInWatch(true);
        toast(t("已加入自选", "Added to watchlist"));
      }
    } catch (e: any) {
      toast(e.message || t("操作失败", "Action failed"));
    } finally {
      setWatchBusy(false);
    }
  };

  const share = async () => {
    try {
      await navigator.clipboard?.writeText(`${location.href}\n${t("历史数据，不构成投资建议。", "Historical data; not investment advice.")}`);
      toast(t("链接已复制 · 含风险提示", "Link copied · includes risk notice"));
    } catch {
      toast(t("复制失败，请手动复制地址栏", "Copy failed; please copy the address bar manually"));
    }
  };

  if (error) {
    return (
      <div className="page stock-page">
        <button className="page-back" onClick={() => nav(-1)} aria-label={t("返回", "Back")}><ArrowLeft size={18} /></button>
        <ErrorState message={error} onRetry={() => load()} />
      </div>
    );
  }
  if (!data) {
    return (
      <div className="page stock-page">
        <button className="page-back" onClick={() => nav(-1)} aria-label={t("返回", "Back")}><ArrowLeft size={18} /></button>
        <LoadingCards rows={4} />
      </div>
    );
  }

  const q = data.quote || {};
  const v = data.valuation || {};
  const tech = data.technical || {};
  const up = Number(q.changePct) >= 0;
  const pct = Math.max(0, Math.min(100, Number(v.pePercentile ?? 50)));
  const news = data.news || [];
  const fund = data.fundFlow || { available: false, series: [], distribution: [] };
  const peers = data.peers || [];
  const statements = data.statements || {};
  const latestFin = (data.financialTrend?.items || []).slice(-1)[0] || {};
  const chartBars = data.chart?.bars || [];
  const subValues = (() => {
    if (subIndicator === "volume" || subIndicator === "amount") {
      const values = chartBars.map((b: any) => Number((subIndicator === "volume" ? b.volume : b.amount) || 0));
      const ma5 = movingAverage(values, 5);
      const ma10 = movingAverage(values, 10);
      return [
        { key: "value", label: subIndicator === "volume" ? t("成交量", "Volume") : t("成交额", "Turnover"), value: formatCompact(values[values.length - 1] ?? null, subIndicator === "volume" ? "vol" : "amount"), color: "red" },
        { key: "ma5", label: "MA5", value: formatCompact(ma5[ma5.length - 1] ?? null, subIndicator === "volume" ? "vol" : "amount"), color: "amber" },
        { key: "ma10", label: "MA10", value: formatCompact(ma10[ma10.length - 1] ?? null, subIndicator === "volume" ? "vol" : "amount"), color: "purple" },
      ];
    }
    if (subIndicator === "macd") {
      const d = macd(chartBars);
      return [
        { key: "dif", label: "DIF", value: formatCompact(latestValue(d.dif), "index"), color: "blue" },
        { key: "dea", label: "DEA", value: formatCompact(latestValue(d.dea), "index"), color: "amber" },
        { key: "macd", label: "MACD", value: formatCompact(latestValue(d.hist), "index"), color: "purple" },
      ];
    }
    if (subIndicator === "kdj") {
      const d = kdj(chartBars);
      return [
        { key: "k", label: "K", value: formatCompact(latestValue(d.k), "index"), color: "blue" },
        { key: "d", label: "D", value: formatCompact(latestValue(d.d), "index"), color: "amber" },
        { key: "j", label: "J", value: formatCompact(latestValue(d.j), "index"), color: "purple" },
      ];
    }
    return [
      { key: "rsi6", label: "RSI6", value: formatCompact(latestValue(rsi(chartBars, 6)), "index"), color: "blue" },
      { key: "rsi12", label: "RSI12", value: formatCompact(latestValue(rsi(chartBars, 12)), "index"), color: "amber" },
      { key: "rsi24", label: "RSI24", value: formatCompact(latestValue(rsi(chartBars, 24)), "index"), color: "purple" },
    ];
  })();
  const tabs = [
    ...(news.length ? [{ key: "news", label: t("资讯", "News") }] : []),
    ...(!isUs && q.asset !== "etf" ? [{ key: "finance", label: t("财务", "Financials") }] : []),
    ...(fund.available ? [{ key: "fund", label: t("资金", "Funds") }] : []),
    { key: "profile", label: t("简况", "Profile") },
  ];
  const activeTab = tabs.some((x) => x.key === tab) ? tab : tabs[0]?.key;
  const board = BOARD_LABEL[q.board] || q.board || displayIndustry(q.industry);

  return (
    <div className="page stock-page">
      <header className="stock-head">
        <button className="round-btn" onClick={() => nav(-1)} aria-label={t("返回", "Back")}><ArrowLeft size={18} /></button>
        <div className="stock-head-title">
          <b>{q.name}</b>
          <span>{q.code} · {displayIndustry(q.industry)} · {board}</span>
        </div>
        <div className="stock-head-actions">
          <button className="round-btn" onClick={() => nav("/search")} aria-label={t("搜个股", "Search stocks")}><Search size={18} /></button>
          <button className="round-btn" onClick={share} aria-label={t("分享", "Share")}><Share2 size={18} /></button>
        </div>
      </header>

      <section className="stock-quote">
        <div className="stock-quote-price">
          <b className={up ? "up" : "down"}>{formatPrice(q.price)}</b>
          <span className={up ? "up" : "down"}>
            {Number(q.change) >= 0 ? "+" : ""}{Number(q.change || 0).toFixed(2)}
            {" "}{fmtPct(q.changePct)}
          </span>
        </div>
        <div className="stock-quote-grid">
          {[
            [t("高", "High"), q.high, "price"],
            [t("低", "Low"), q.low, "price"],
            [t("开", "Open"), q.open, "price"],
            [t("市值", "Mkt cap"), fmtMarketCap(q.marketCap), "plain"],
            [t("流通", "Float"), fmtMarketCap(q.floatMarketCap), "plain"],
            [t("市盈", "P/E"), q.pe != null ? Number(q.pe).toFixed(2) : "—", "plain"],
            [t("量比", "Vol ratio"), q.volumeRatio != null ? Number(q.volumeRatio).toFixed(2) : "—", "plain"],
            [t("换手", "Turnover"), q.turnover != null ? `${Number(q.turnover).toFixed(2)}%` : "—", "plain"],
            [t("额", "Amount"), fmtMoney(q.amount), "plain"],
          ].map(([label, value, kind], i) => {
            const numeric = value === null || value === undefined || value === "—" ? NaN : Number(value);
            const relative = Number.isFinite(numeric) && numeric >= Number(q.prevClose ?? q.price);
            const tone = kind === "price" && Number.isFinite(numeric) ? (relative ? "up" : "down") : "";
            return <div className={`stock-quote-cell ${tone}`} key={`${label}-${i}`}><span>{label}</span><b>{kind === "price" ? formatPrice(value) : value}</b></div>;
          })}
        </div>
      </section>

      <section className="card chart-card">
        <div className="card-title-row">
          <h2>{t("走势", "Price")}</h2>
          <span className="hint">{data.dataDate} · {t("收盘 · 非实时", "Close · not real-time")}</span>
        </div>
        <div className="seg period-seg">
          {PERIODS.map((p) => (
            <button key={p.key} className={period === p.key ? "on" : ""} onClick={() => changePeriod(p.key)}>{t(p.zh, p.en)}</button>
          ))}
        </div>
        <div className="chart-topline">
          <div className="chart-indicator-switch">
            <button className={indicator === "ma" ? "on" : ""} onClick={() => setIndicator("ma")}>{t("均线", "MA")}</button>
            <button className={indicator === "boll" ? "on" : ""} onClick={() => setIndicator("boll")}>BOLL</button>
          </div>
          <div className="chart-legend chart-legend-top">
            <span><i className="legend-red" />{t("K 线", "Candles")}</span>
            {indicator === "ma" ? (
              <>
                <span><i className="legend-amber" />MA5</span>
                <span><i className="legend-purple" />MA10</span>
                <span><i className="legend-blue" />MA20</span>
              </>
            ) : (
              <>
                <span><i className="legend-amber" />MID</span>
                <span><i className="legend-red" />UP</span>
                <span><i className="legend-blue" />LOW</span>
              </>
            )}
          </div>
        </div>
        <Suspense fallback={<div className="kline-loading">{t("加载图表…", "Loading chart…")}</div>}>
          <KLineChart
            bars={data.chart?.bars || []}
            ma5={data.chart?.ma5 || []}
            ma10={data.chart?.ma10 || []}
            ma20={data.chart?.ma20 || []}
            indicator={indicator}
            range={chartRange}
            onRangeChange={setChartRange}
            height={230}
          />
        </Suspense>
        <div className="volume-topline">
          <div className="chart-indicator-switch sub-indicator-switch">
            {SUB_INDICATORS.map((item) => (
              <button key={item.key} className={subIndicator === item.key ? "on" : ""} onClick={() => setSubIndicator(item.key)}>
                {t(item.zh, item.en)}
              </button>
            ))}
          </div>
          <div className="chart-legend sub-legend">
            {subValues.map((item) => (
              <span key={item.key}><i className={`legend-${item.color}`} />{item.label} {item.value}</span>
            ))}
          </div>
        </div>
        <Suspense fallback={<div className="volume-empty">{t("加载副图…", "Loading sub-chart…")}</div>}>
          <VolumeChart
            bars={chartBars}
            indicator={subIndicator}
            range={chartRange}
            onRangeChange={setChartRange}
            height={118}
          />
        </Suspense>
        <div className="hint">{t("日/周/月 K 由收盘数据聚合；前复权口径。", "Daily/weekly/monthly candles are aggregated from EOD data; forward-adjusted.")}</div>
      </section>

      {!isUs ? (
        <AiPanel
          title={t("AI 个股五维分析", "AI 5-dim stock analysis")}
          subtitle={t("自动生成基本面、盈利、估值、风险、资金五个分点结论，不展示图表，不给买卖建议。", "Five point conclusions on fundamentals, profitability, valuation, risk and capital; no charts and no buy/sell advice.")}
          endpoint={`/api/invest/ai/stock/${code}`}
          hideOnError
          blocksMode
          expandable
        />
      ) : null}

      <div className="seg stock-seg">
        {tabs.map((x) => <button key={x.key} className={activeTab === x.key ? "on" : ""} onClick={() => setTab(x.key)}>{x.label}</button>)}
      </div>

      {activeTab === "news" ? (
        <section className="card">
          <div className="card-title-row">
            <h2>{t("资讯", "News")}</h2>
            {news.length > 4 ? <button className="link-btn" onClick={() => setNewsOpen(true)}>{t("查看全部", "All")} <ChevronRight size={14} /></button> : null}
          </div>
          <div className="news-list">
            {news.slice(0, 4).map((n: any) => (
              <a className="news-item" key={n.id} href={n.url} target="_blank" rel="noreferrer">
                <b>{n.title}</b>
                <span>{n.source} · {n.published_at}</span>
              </a>
            ))}
          </div>
        </section>
      ) : null}

      {activeTab === "finance" ? (
        <>
          <section className="card">
            <div className="card-title-row"><h2>{t("财务指标趋势", "Financial trend")}</h2><span className="hint">{t("同类型报告期累计", "Cumulative, same report period")}</span></div>
            <FinancialTrend items={data.financialTrend?.items || []} />
          </section>
          <section className="card">
            <div className="card-title-row"><h2>{t("财务报表", "Statements")}</h2><span className="hint">{t("三张表", "Three statements")}</span></div>
            <div className="stock-links">
              <button onClick={() => setStatementOpen(true)}>{t("利润表", "Income statement")} <ChevronRight size={14} /></button>
              <button onClick={() => setStatementOpen(true)}>{t("资产负债表", "Balance sheet")} <ChevronRight size={14} /></button>
              <button onClick={() => setStatementOpen(true)}>{t("现金流量表", "Cash flow statement")} <ChevronRight size={14} /></button>
            </div>
          </section>
          <section className="card">
            <div className="card-title-row"><h2>{t("估值水平", "Valuation")}</h2><span className="hint">{t("近 3 年分位", "3-year percentile")}</span></div>
            <div className="valuation-nums">
              <div><span>PE(TTM)</span><b>{v.pe != null ? `${Number(v.pe).toFixed(2)}x` : "—"}</b>{v.industryPe != null ? <small>{t("行业", "Industry")} {Number(v.industryPe).toFixed(2)}x</small> : null}</div>
              <div><span>PB</span><b>{v.pb != null ? `${Number(v.pb).toFixed(2)}x` : "—"}</b>{v.pbPercentile != null ? <small>{t("分位", "Percentile")} {Number(v.pbPercentile).toFixed(1)}%</small> : null}</div>
              <div><span>{t("股息率", "Dividend yield")}</span><b>{q.dividendYield != null ? `${Number(q.dividendYield).toFixed(2)}%` : "—"}</b></div>
            </div>
            <div className="valuation-track"><i style={{ left: `${pct}%` }} /></div>
            <div className="valuation-labels"><span>{t("历史低位", "Low")}</span><span>{t("当前", "Now")} {v.pePercentile != null ? `${Number(v.pePercentile).toFixed(1)}%` : "—"}</span><span>{t("历史高位", "High")}</span></div>
            <p className="hint">{t("PE 分位只描述历史位置；低分位不等于安全边际。", "PE percentile only describes history; low is not a margin of safety.")}</p>
          </section>
        </>
      ) : null}

      {activeTab === "fund" ? (
        <>
          <section className="card">
            <div className="card-title-row"><h2>{t("主力资金", "Main capital")}</h2><span className="hint">{t("大单 + 特大单", "Large + super large")}</span></div>
            <div className="fund-kpis">
              <div><span>{t("今日", "Today")}</span><b className={Number(fund.latest) >= 0 ? "up" : "down"}>{fund.latest != null ? `${Number(fund.latest) >= 0 ? "+" : ""}${Number(fund.latest).toFixed(2)} 亿` : "—"}</b></div>
              <div><span>{t("5 日", "5-day")}</span><b className={Number(fund.five_day) >= 0 ? "up" : "down"}>{fund.five_day != null ? `${Number(fund.five_day) >= 0 ? "+" : ""}${Number(fund.five_day).toFixed(2)} 亿` : "—"}</b></div>
              <div><span>{t("20 日", "20-day")}</span><b className={Number(fund.twenty_day) >= 0 ? "up" : "down"}>{fund.twenty_day != null ? `${Number(fund.twenty_day) >= 0 ? "+" : ""}${Number(fund.twenty_day).toFixed(2)} 亿` : "—"}</b></div>
            </div>
          </section>
          <section className="card">
            <div className="card-title-row"><h2>{t("资金分布", "Flow distribution")}</h2><span className="hint">{t("当日净额", "Today's net")}</span></div>
            <FundDistribution rows={fund.distribution || []} />
          </section>
          {(fund.series || []).length >= 20 ? (
            <section className="card">
              <div className="card-title-row"><h2>{t("近 20 日主力净流入", "20-day main net inflow")}</h2><span className="hint">{t("红入 / 绿出", "Red in / green out")}</span></div>
              <FundFlowChart points={fund.series || []} />
              <div className="chart-legend fund-flow-legend">
                <span><i className="legend-red" />{t("流入", "Inflow")}</span>
                <span><i className="legend-green" />{t("流出", "Outflow")}</span>
                <span className="hint">{t("单位：亿元", "Unit: CNY 100m")}</span>
              </div>
            </section>
          ) : null}
          {fund.divergence ? <div className="callout blue">{fund.divergence.text}</div> : null}
        </>
      ) : null}

      {activeTab === "profile" ? (
        <>
          <section className="card">
            <div className="card-title-row"><h2>{t("基本信息", "Basics")}</h2></div>
            <div className="stock-basic-grid">
              <Kv k={t("上市日期", "Listed")} v={q.listDate || "—"} />
              <Kv k={t("上市地", "Exchange")} v={q.exchange || "—"} />
              <Kv k={t("总股本", "Total shares")} v={fmtShares(q.totalShares)} />
              <Kv k={t("流通股本", "Float shares")} v={fmtShares(q.floatShares)} />
            </div>
          </section>
          {peers.length ? (
            <section className="card">
              <div className="card-title-row"><h2>{t("同业比较", "Peers")}</h2><span className="hint">{t("按总市值", "By market cap")}</span></div>
              <div className="table-wrap">
                <table className="data-table">
                  <thead><tr><th>{t("名称", "Name")}</th><th>{t("最新价", "Price")}</th><th>{t("涨跌", "Change")}</th><th>PE</th><th>{t("市值", "Mkt cap")}</th></tr></thead>
                  <tbody>
                    {peers.map((p: any) => (
                      <tr key={p.code} onClick={() => nav(`/stock/${p.code}`)}>
                        <td>{p.name}</td>
                        <td>{formatPrice(p.price)}</td>
                        <td className={Number(p.changePct) >= 0 ? "up" : "down"}>{fmtPct(p.changePct)}</td>
                        <td>{p.pe != null ? Number(p.pe).toFixed(1) : "—"}</td>
                        <td>{fmtMarketCap(p.marketCap)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}
          <section className="card">
            <div className="card-title-row"><h2>{t("主要风险", "Key risks")}</h2><span className="hint">{t("规则归纳", "Rule-based")}</span></div>
            <div className="risk-list">
              {(data.risks || []).slice(0, 4).map((r: any, i: number) => (
                <div className="risk-item" key={i}>
                  <span className={`risk-dot ${r.level}`} />
                  <div><b>{r.title}</b><p>{r.detail}</p></div>
                </div>
              ))}
            </div>
          </section>
          {q.asset === "etf" ? (
            <button className="link-btn" onClick={() => nav(`/etf/${code}`)}>{t("查看 ETF 穿透", "ETF look-through")} <ChevronRight size={14} /></button>
          ) : null}
        </>
      ) : null}

      <Disclaimer>{data.dataSource || t("收盘数据", "EOD data")} · {t("非实时 · 不构成投资建议", "not real-time · not investment advice")}</Disclaimer>

      <div className="stock-cta">
        <button className="btn btn-ghost" onClick={() => nav("/ai")}>{t("问 AI", "Ask AI")}</button>
        <button className={`btn ${inWatch ? "btn-ghost" : "btn-primary"}`} onClick={toggleWatch} disabled={watchBusy}>
          {inWatch ? t("已加自选", "In watchlist") : t("加自选", "Add to watchlist")}
        </button>
      </div>

      <Sheet open={newsOpen} onClose={() => setNewsOpen(false)} title={t("个股资讯", "Stock news")} sub={t("标题 + 来源", "Titles + sources")}>
        <div className="news-list">
          {news.map((n: any) => (
            <a className="news-item" key={n.id} href={n.url} target="_blank" rel="noreferrer">
              <b>{n.title}</b>
              <p>{n.summary}</p>
              <span>{n.source} · {n.published_at}</span>
            </a>
          ))}
        </div>
      </Sheet>


      <Sheet open={statementOpen} onClose={() => setStatementOpen(false)} title={t("三大报表", "Three statements")} sub={statements.period || ""}>
        <div className="statement-list">
          <div>
            <b>{t("利润表", "Income statement")}</b>
            {statements.income ? (
              <p>{t("营收", "Revenue")} {Number(statements.income.revenue).toFixed(1)} {t("亿", "100m")} · {t("归母净利", "Net profit")} {Number(statements.income.netProfit).toFixed(1)} {t("亿", "100m")} · {t("毛利率", "Gross margin")} {statements.income.grossMargin != null ? `${Number(statements.income.grossMargin).toFixed(1)}%` : "—"} · {t("净利率", "Net margin")} {latestFin.net_margin != null ? `${Number(latestFin.net_margin).toFixed(1)}%` : "—"}</p>
            ) : <p className="hint">{t("暂无利润表", "No income statement")}</p>}
          </div>
          <div>
            <b>{t("资产负债表", "Balance sheet")}</b>
            {statements.balance ? (
              <p>{t("总资产", "Assets")} {fmtYi(statements.balance.total_assets)} · {t("总负债", "Liabilities")} {fmtYi(statements.balance.total_liabilities)} · {t("净资产", "Equity")} {fmtYi(statements.balance.total_equity)} · {t("资产负债率", "Debt ratio")} {statements.balance.total_assets ? `${(Number(statements.balance.total_liabilities) / Number(statements.balance.total_assets) * 100).toFixed(1)}%` : "—"}</p>
            ) : <p className="hint">{t("暂无资产负债表", "No balance sheet")}</p>}
          </div>
          <div>
            <b>{t("现金流量表", "Cash flow statement")}</b>
            {statements.cashflow ? (
              <p>{t("经营", "Operating")} {fmtYi(statements.cashflow.operating_cf)} · {t("投资", "Investing")} {fmtYi(statements.cashflow.investing_cf)} · {t("筹资", "Financing")} {fmtYi(statements.cashflow.financing_cf)}</p>
            ) : <p className="hint">{t("暂无现金流量表", "No cash flow statement")}</p>}
          </div>
        </div>
      </Sheet>

      <GlossarySheet open={glossary} onClose={() => setGlossary(false)} />
    </div>
  );
}
