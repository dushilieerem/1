import { lazy, Suspense, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ChevronRight, FileText, Share2, Star, TrendingDown, TrendingUp, X } from "lucide-react";
import { api } from "../api";
import { Disclaimer, ErrorState, Kv, LoadingCards, PageHeader, Sheet, Tag } from "../components";
import { displayIndustry, fmtMarketCap, fmtMoney, fmtPct, fmtShares, formatPrice } from "../lib";
import { useToast } from "../toast";
import GlossarySheet from "../GlossarySheet";
import AiPanel from "../components/AiPanel";
import { AiCard } from "../components/AiCard";
import { useLocale, withMarket } from "../i18n";

const KLineChart = lazy(() => import("../KLineChart"));

const PERIODS = [
  { key: "minute", zh: "分时", en: "Intraday" },
  { key: "daily", zh: "日K", en: "D" },
  { key: "weekly", zh: "周K", en: "W" },
  { key: "monthly", zh: "月K", en: "M" },
];
function MinuteChart({ items }: { items: any[] }) {
  const { t } = useLocale();
  const closes = items.map((x) => Number(x.close)).filter((x) => Number.isFinite(x));
  if (!closes.length) return <div className="empty-inline">{t("暂无有效分时价", "No valid intraday prices")}</div>;
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const span = max - min || 1;
  const w = 320;
  const h = 140;
  const step = w / Math.max(1, closes.length - 1);
  const points = closes.map((v, i) => `${(i * step).toFixed(2)},${(h - ((v - min) / span) * (h - 12) - 6).toFixed(2)}`).join(" ");
  const first = closes[0];
  const last = closes[closes.length - 1];
  const up = last >= first;
  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label={t("分时走势", "Intraday chart")} style={{ width: "100%", height: 170 }}>
        <polyline
          points={points}
          fill="none"
          stroke={up ? "#d14343" : "#1f9d55"}
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
      </svg>
      <div className="chart-legend">
        <span>{t("最新", "Last")} {formatPrice(last)}</span>
        <span>{t("最高", "High")} {formatPrice(max)}</span>
        <span>{t("最低", "Low")} {formatPrice(min)}</span>
        <span>{up ? t("上涨", "Up") : t("下跌", "Down")} {(((last - first) / first) * 100).toFixed(2)}%</span>
      </div>
    </div>
  );
}

const TABS = [
  { key: "overview", zh: "概览", en: "Overview" },
  { key: "finance", zh: "财务", en: "Financials" },
  { key: "valuation", zh: "估值", en: "Valuation" },
  { key: "risk", zh: "风险", en: "Risk" },
];

function Help({ term }: { term: string }) {
  const { t } = useLocale();
  const nav = useNavigate();
  return (
    <button className="metric-help" title={t("查看术语", "View glossary")} onClick={() => nav(`/learn?term=${term}`)}>?</button>
  );
}

function FinancialBars({ fins }: { fins: any[] }) {
  const { t } = useLocale();
  if (!fins.length) return <div className="empty-inline">{t("暂无财务数据", "No financial data")}</div>;
  const rows = fins.slice(-4);
  const max = Math.max(...rows.map((r) => r.revenue || 0), 1);
  return (
    <div className="fin-bars">
      {rows.map((r) => (
        <div className="fin-row" key={r.period}>
          <span className="fin-period">{r.period.replace("Q", " Q")}</span>
          <div className="fin-track">
            <i style={{ width: `${Math.max(4, (r.revenue / max) * 100)}%` }} />
          </div>
          <span className="fin-value">{r.revenue?.toFixed?.(0) ?? r.revenue}</span>
        </div>
      ))}
      <div className="hint">{t("营业收入（亿元）· 规则展示，非预测", "Revenue (CNY 100m) · rule-based display, not a forecast")}</div>
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
  const [period, setPeriod] = useState("daily");
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState("overview");
  const [newsOpen, setNewsOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [glossary, setGlossary] = useState(false);
  const [inWatch, setInWatch] = useState(false);
  const [watchBusy, setWatchBusy] = useState(false);
  const [minute, setMinute] = useState<any[] | null>(null);
  const [minuteError, setMinuteError] = useState<string | null>(null);
  const [minuteLoading, setMinuteLoading] = useState(false);
  const [annAi, setAnnAi] = useState<any>(null);
  const [annBusy, setAnnBusy] = useState<string | null>(null);

  const load = (nextPeriod = period) => {
    setError(null);
    setLoading(true);
    api(`/api/invest/stock/${code}?period=${nextPeriod}`)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    setData(null);
    setTab("overview");
    load(period);
  }, [code]);

  useEffect(() => {
    api<any>(withMarket("/api/invest/watchlist", market))
      .then((w) => setInWatch((w.groups || []).some((g: any) => g.items.some((i: any) => i.code === code))))
      .catch(() => {});
  }, [code, market]);

  const loadMinute = () => {
    setMinuteLoading(true);
    setMinuteError(null);
    api<{ items: any[] }>(`/api/market-data/minute/${code}?freq=1m&limit_days=1`)
      .then((d) => setMinute(d.items || []))
      .catch((e) => setMinuteError(e.message))
      .finally(() => setMinuteLoading(false));
  };

  const changePeriod = (p: string) => {
    if (p === period) return;
    if (isUs && p === "minute") return;
    setPeriod(p);
    if (p === "minute") loadMinute();
    else load(p);
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
      await navigator.clipboard?.writeText(location.href);
      toast(t("链接已复制 · 含风险提示", "Link copied · includes risk notice"));
    } catch {
      toast(t("复制失败，请手动复制地址栏", "Copy failed; please copy the address bar manually"));
    }
  };

  if (error) {
    return (
      <div className="page">
        <PageHeader title={t("个股", "Stock")} back onBack={() => nav(-1)} />
        <ErrorState message={error} onRetry={() => load()} />
      </div>
    );
  }
  if (!data) {
    return (
      <div className="page">
        <PageHeader title={t("个股", "Stock")} back onBack={() => nav(-1)} />
        <LoadingCards rows={4} />
      </div>
    );
  }

  const q = data.quote;
  const tech = data.technical;
  const v = data.valuation;
  const up = q.changePct >= 0;
  const peer = v.industryPe;
  const pct = Math.max(0, Math.min(100, v.pePercentile ?? 50));

  return (
    <div className="page stock-page">
      <PageHeader
        title={q.name}
        sub={`${q.code} · ${displayIndustry(q.industry)}`}
        back
        onBack={() => nav(-1)}
        right={
          <>
            <button className={`round-btn ${inWatch ? "active" : ""}`} onClick={toggleWatch} aria-label={t("自选", "Watchlist")}>
              <Star size={18} fill={inWatch ? "currentColor" : "none"} />
            </button>
            <button className="round-btn" onClick={share} aria-label={t("分享", "Share")}><Share2 size={18} /></button>
          </>
        }
      />

      <div className="topic-tags">
        <Tag tone="red">{t("收盘数据", "EOD data")}</Tag>
        <Tag tone="gray">{t("非实时", "Not real-time")}</Tag>
        <Tag tone={data.isDemo ? "gray" : "green"}>{data.isDemo ? t("演示数据", "Demo data") : t("公开数据", "Public data")}</Tag>
        {!isUs ? <button className="link-btn" onClick={() => nav(`/compare/${code}`)}>{t("对比", "Compare")}</button> : null}
      </div>

      <section className="ai-summary-card">
        <div className="ai-summary-head">
          <b>{t("数据摘要", "Data summary")}</b>
          <span>{t("规则生成 · 非投资建议", "Rule-based · not investment advice")}</span>
        </div>
        <ul className="fact-list">
          {data.summary.map((line: string, i: number) => <li key={i}>{line}</li>)}
        </ul>
        <button className="link-btn" onClick={() => setTab("risk")}>{t("查看风险", "View risks")} <ChevronRight size={14} /></button>
      </section>

      {data.behavior?.triggered ? (
        <section className="card behavior-card">
          <div className="card-title-row"><h2>{t("追高提醒", "Chase-high warning")}</h2><span className="hint">{t("行为护栏 · 非预测", "Behavior guard · not a forecast")}</span></div>
          <p>{data.behavior.reasons?.join(t("；", "; "))}</p>
          <p className="hint">
            {data.behavior.baseRate?.sample
              ? t(
                  `${data.behavior.baseRate.period}：类似情况 ${data.behavior.baseRate.sample} 次，20 日中位收益 ${data.behavior.baseRate.medianReturn}%，中位最大回撤 ${data.behavior.baseRate.maxDrawdown}%，上涨占比 ${data.behavior.baseRate.winRate}%。`,
                  `${data.behavior.baseRate.period}: ${data.behavior.baseRate.sample} similar cases; median 20-day return ${data.behavior.baseRate.medianReturn}%, median max drawdown ${data.behavior.baseRate.maxDrawdown}%, win rate ${data.behavior.baseRate.winRate}%.`,
                )
              : t("历史样本不足，无法给出 base rate。", "Not enough history for a base rate.")}
          </p>
          <p className="hint">{t("热度与估值是两件事；历史分布不是预测。", "Heat and valuation are different things; historical distributions are not forecasts.")}</p>
        </section>
      ) : null}

      {!isUs ? (
        <AiPanel
          title={t("AI 个股结论", "AI stock takeaway")}
          subtitle={t("自动生成，50 字以内，只解释数据，不给买卖建议。", "Generated automatically in under 50 characters; explains data, never buy/sell advice.")}
          endpoint={`/api/invest/ai/stock/${code}`}
        />
      ) : null}

      <section className="quote-card">
        <div className="quote-main">
          <div>
            <b className={up ? "up" : "down"}>{formatPrice(q.price)}</b>
            <span className={up ? "up" : "down"}>
              {up ? <TrendingUp size={14} /> : <TrendingDown size={14} />} {fmtPct(q.changePct)} · {q.change >= 0 ? "+" : ""}{q.change.toFixed(2)}
            </span>
          </div>
          <span className="quote-date">{t(`${data.dataDate} 收盘`, `${data.dataDate} close`)}</span>
        </div>
        <div className="quote-grid">
          <div><span>{t("最高", "High")}</span><b>{formatPrice(q.high)}</b></div>
          <div><span>{t("最低", "Low")}</span><b>{formatPrice(q.low)}</b></div>
          <div><span>{t("今开", "Open")}</span><b>{formatPrice(q.open)}</b></div>
          <div><span>{t("昨收", "Prev close")}</span><b>{formatPrice(q.prevClose)}</b></div>
          <div title={t("优先总市值，缺失时回退流通市值；单位亿元", "Total market cap preferred, falls back to float cap; unit CNY 100m")}>
            <span>{t("总市值", "Market cap")}</span><b>{fmtMarketCap(q.marketCap)}</b>
          </div>
          <div><span>{t("换手率", "Turnover")}</span><b>{q.turnover != null ? `${q.turnover.toFixed(2)}%` : "—"}</b></div>
          <div><span>{t("成交额（元）", "Amount (CNY)")}</span><b>{fmtMoney(q.amount)}</b></div>
          <div><span>{t("成交量", "Volume")}</span><b>{fmtShares(q.volume)}</b></div>
          <div><span>PE(TTM)</span><b>{q.pe?.toFixed?.(2) ?? "—"}</b></div>
          <div><span>PB</span><b>{q.pb?.toFixed?.(2) ?? "—"}</b></div>
        </div>
        <p className="hint">
          {isUs
            ? t("美股当前不提供市值、PE/PB 与换手率；显示 — 表示数据未接入，不是 0。成交量单位：股。", "Market cap, PE/PB and turnover are not available for US names; — means missing, not zero. Volume is in shares.")
            : t("市值单位：亿元（优先总市值，缺失回退流通市值）；成交额单位：元；成交量单位：股；— 表示缺失，不填 0。", "Market cap in CNY 100m (total preferred, float as fallback); amount in CNY; volume in shares; — means missing, not zero.")}
        </p>
      </section>

      <section className="card chart-card">
        <div className="card-title-row">
          <h2>{t("行情走势", "Price chart")}</h2>
          <span className="hint">{period === "minute" ? t("分时 · 非实时", "Intraday · not real-time") : t("收盘数据 · 非实时", "EOD · not real-time")}</span>
        </div>
        <div className="seg period-seg">
          {PERIODS.filter((p) => !isUs || p.key !== "minute").map((p) => (
            <button key={p.key} className={period === p.key ? "on" : ""} onClick={() => changePeriod(p.key)}>
              {t(p.zh, p.en)}
            </button>
          ))}
        </div>
        {period === "minute" ? (
          minuteLoading ? (
            <div className="kline-loading">{t("加载分时…", "Loading intraday…")}</div>
          ) : minuteError ? (
            <div className="empty-inline">{t(`分时数据不可用：${minuteError}`, `Intraday data unavailable: ${minuteError}`)}</div>
          ) : minute?.length ? (
            <MinuteChart items={minute} />
          ) : (
            <div className="empty-inline">{t("暂无分时数据（仅支持 2025 年以来的交易日）", "No intraday data yet (only sessions since 2025 are supported).")}</div>
          )
        ) : loading ? <div className="kline-loading">{t("加载行情…", "Loading quotes…")}</div> : isUs && !data.chart.bars.length ? (
          <div className="empty-inline">
            {t(
              "美股当前只有最新价快照，日线 K 线未接入；价格、成交额与换手率仍来自快照。",
              "US mode currently provides a latest-price snapshot only; daily bars are not connected. Price, amount and turnover still come from the snapshot.",
            )}
          </div>
        ) : (
          <Suspense fallback={<div className="kline-loading">{t("加载图表…", "Loading chart…")}</div>}>
            <KLineChart bars={data.chart.bars} ma5={data.chart.ma5} ma10={data.chart.ma10} ma20={data.chart.ma20} />
          </Suspense>
        )}
        <div className="chart-legend">
          <span><i className="legend-red" />{t("K 线", "Candles")}</span>
          <span><i className="legend-amber" />MA5</span>
          <span><i className="legend-purple" />MA10</span>
          <span><i className="legend-blue" />MA20</span>
        </div>
        <details className="chart-data">
          <summary>{t("查看最近 5 根 K 线数据", "Latest 5 bars")}</summary>
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>{t("日期", "Date")}</th><th>{t("收盘", "Close")}</th><th>{t("最高", "High")}</th><th>{t("最低", "Low")}</th></tr></thead>
              <tbody>
                {data.chart.bars.slice(-5).reverse().map((b: any) => (
                  <tr key={b.time}><td>{b.time}</td><td>{b.close}</td><td>{b.high}</td><td>{b.low}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
        <div className="hint">{t("日/周/月 K 由收盘数据聚合；前复权口径。图表引擎：TradingView Lightweight Charts。", "Daily/weekly/monthly candles are aggregated from EOD data; forward-adjusted. Chart engine: TradingView Lightweight Charts.")}</div>
        {code && /^(5[168]|1[56])\d{4}$/.test(code) ? (
          <Link to={`/etf/${code}`} className="link-btn" style={{ marginTop: 8, display: "inline-flex" }}>
            {t("查看 ETF 穿透", "ETF look-through")}
          </Link>
        ) : null}
      </section>

      <section className="card tech-card">
        <div className="card-title-row"><h2>{t("技术面速览", "Technical snapshot")}</h2><span className="hint">{t("基于日 K", "Based on daily bars")}</span></div>
        <div className="tech-row"><span>{t("价格趋势", "Trend")}</span><b>{tech.trend}</b><em>{t("回撤", "Drawdown")} {fmtPct(tech.drawdown, 1)} · {t("20 日", "20-day")} {fmtPct(tech.return20, 1)}</em></div>
        <div className="tech-row"><span>{t("均线系统", "Moving averages")}</span><b>MA20 {tech.ma20 ? formatPrice(tech.ma20) : t("待补充", "N/A")}</b><em>MA5 {tech.ma5 ? formatPrice(tech.ma5) : t("待补充", "N/A")} · MA10 {tech.ma10 ? formatPrice(tech.ma10) : t("待补充", "N/A")}</em></div>
        <div className="tech-row"><span>{t("成交量", "Volume")}</span><b>{tech.volumeRatio?.toFixed?.(1)}x</b><em>{t("相对 20 日均量", "vs 20-day average")}</em></div>
        <p className="hint">
          {t(
            "趋势 = 现价相对 MA20；回撤 = 距近 180 日高点；量比 = 当前成交量相对 20 日均量；均线显示待补充表示历史不足 20 个交易日。",
            "Trend = price vs MA20; drawdown = from the 180-day high; volume ratio = current volume vs the 20-day average; N/A on moving averages means fewer than 20 trading days of history.",
          )}
        </p>
      </section>

      <div className="seg stock-seg">
        {TABS.map((x) => (
          <button key={x.key} className={tab === x.key ? "on" : ""} onClick={() => setTab(x.key)}>{t(x.zh, x.en)}</button>
        ))}
      </div>

      {tab === "overview" && (
        <section className="card">
          <div className="card-title-row"><h2>{t("关键跟踪", "Key tracking")}</h2><span className="hint">{t("规则标签", "Rule tags")}</span></div>
          <div className="risk-list compact">
            {data.risks.map((r: any, i: number) => (
              <div className="risk-item" key={i}>
                <span className={`risk-dot ${r.level}`} />
                <div><b>{r.title}</b><p>{r.detail}</p></div>
              </div>
            ))}
          </div>
          <div className="divider" />
          <Kv k={t("行业", "Industry")} v={displayIndustry(q.industry)} />
          <Kv k={<span>Beta <Help term="beta" /></span>} v={q.beta != null ? (Math.abs(q.beta) < 0.005 ? "0.00" : q.beta.toFixed(2)) : t("风险指标待补充", "Risk metric pending")} />
          <Kv k={<span>{t("股息率", "Dividend yield")} <Help term="dividend_yield" /></span>} v={q.dividendYield != null ? `${q.dividendYield.toFixed(2)}%` : t("待补充", "Pending")} />
          <Kv
            k={t("下次财报（预计）", "Next report (est.)")}
            v={
              q.nextReportDate ||
              (q.nextReportDateAvailable === false
                ? t("暂无可靠未来日历", "No reliable forward calendar")
                : t("待补充", "Pending"))
            }
          />
          {q.beta == null || !q.nextReportDate ? (
            <p className="hint">
              {t(
                "Beta 来自风险日表，缺失时显示「待补充」；预计财报日暂无可靠免费未来日历，显示「暂无可靠未来日历」不代表没有财报。",
                "Beta comes from the risk daily table and shows as pending when missing. There is no reliable free forward calendar for the next report date; “No reliable forward calendar” does not mean no report exists.",
              )}
            </p>
          ) : null}
        </section>
      )}

      {tab === "overview" && data.sentiment?.available ? (
        <section className="card">
          <div className="card-title-row"><h2>{t("舆情与情绪", "News sentiment")}</h2><span className="hint">{t("规则估算 · 非全量舆情", "Rule-based estimate · not full coverage")}</span></div>
          <div className="kpi-grid">
            <div className="kpi"><span>{t("热度", "Heat")}</span><b>{data.sentiment.heat}</b></div>
            <div className="kpi"><span>{t("偏正面", "Positive")}</span><b>{data.sentiment.positive}%</b></div>
            <div className="kpi"><span>{t("偏负面", "Negative")}</span><b>{data.sentiment.negative}%</b></div>
            <div className="kpi"><span>{t("中性/分歧", "Neutral / mixed")}</span><b>{data.sentiment.neutral}%</b></div>
          </div>
          <p className="muted small">{t("当前判断：", "Current read: ")}{data.sentiment.label}；{data.sentiment.note}</p>
          {data.sentiment.topEvent ? <p className="hint">{t("代表事件：", "Top event: ")}{data.sentiment.topEvent}</p> : null}
        </section>
      ) : null}

      {tab === "finance" && (
        <section className="card">
          <div className="card-title-row">
            <h2>{t("财务趋势", "Financial trend")}</h2>
            {!isUs ? <button className="link-btn" onClick={() => setReportOpen(true)}>{t("查看财报", "View report")} <ChevronRight size={14} /></button> : null}
          </div>
          {isUs ? <div className="empty-inline">{t("美股暂无财务数据源；当前只提供行情与 K 线。", "US financial data is not available (no free stable source); this build only provides quotes and charts.")}</div> : q.asset === "etf" ? <div className="empty-inline">{t("ETF 不适用公司财务指标。", "Company financial metrics do not apply to ETFs.")}</div> : (
            <>
              {data.earningsFlash?.available ? (
                <div className="flash-card">
                  <div><b>{t("财报速读", "Earnings flash")}</b><span className="hint">{data.earningsFlash.period}</span></div>
                  <div className="flash-cols">
                    <div><span className="up">{t("亮点", "Highlights")}</span><ul>{data.earningsFlash.highlights.map((x: string) => <li key={x}>{x}</li>)}</ul></div>
                    <div><span className="down">{t("隐忧", "Concerns")}</span><ul>{data.earningsFlash.concerns.map((x: string) => <li key={x}>{x}</li>)}</ul></div>
                  </div>
                  <p className="hint">{data.earningsFlash.consensusGap}</p>
                </div>
              ) : null}
              <FinancialBars fins={data.financials} />
              <div className="table-wrap">
                <table className="data-table">
                  <thead><tr><th>{t("报告期", "Period")}</th><th>{t("营收", "Revenue")}</th><th>{t("同比", "YoY")}</th><th>{t("归母净利", "Net profit")}</th><th>{t("毛利率", "Gross margin")} <Help term="gross_margin" /></th></tr></thead>
                  <tbody>
                    {data.financials.slice(-4).reverse().map((f: any) => (
                      <tr key={f.period}>
                        <td>{f.period}</td>
                        <td>{f.revenue?.toFixed?.(0)}</td>
                        <td className={f.revenue_yoy >= 0 ? "up" : "down"}>{fmtPct(f.revenue_yoy, 1)}</td>
                        <td>{f.net_profit?.toFixed?.(0)}</td>
                        <td>{f.gross_margin?.toFixed?.(1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="hint">{t("单位：亿元；按报告期披露，存在滞后。", "Unit: CNY 100m; reported by period and may lag.")}</div>
            </>
          )}
        </section>
      )}

      {tab === "valuation" && (
        <section className="card">
          <div className="card-title-row"><h2>{t("估值位置", "Valuation")}</h2><span className="hint">{t("近 3 年历史分位", "3-year percentile")}</span></div>
          {isUs ? <div className="empty-inline">{t("美股暂无估值数据源；当前只提供行情与 K 线。", "US valuation data is not available (no free stable source); this build only provides quotes and charts.")}</div> : (
          <>
          <div className="valuation-nums">
            <div><span>PE(TTM)<Help term="pe_ttm" /></span><b>{v.pe?.toFixed?.(2) ?? "—"}x</b></div>
            <div><span>PB<Help term="pb" /></span><b>{v.pb?.toFixed?.(2) ?? "—"}x</b></div>
            <div><span>{t("行业 PE", "Industry PE")}</span><b>{peer?.toFixed?.(2) ?? "—"}x</b></div>
          </div>
          <div className="valuation-track">
            <i style={{ left: `${pct}%` }} />
          </div>
          <div className="valuation-labels"><span>{t("历史低位", "Low")}</span><span>{t("当前", "Now")} {v.pePercentile?.toFixed?.(1) ?? "—"}%</span><span>{t("历史高位", "High")}</span></div>
          <p className="muted small">
            {t(
              `PE 分位 ${v.pePercentile?.toFixed?.(1) ?? "—"}%，PB 分位 ${v.pbPercentile?.toFixed?.(1) ?? "—"}%；样本 ${v.samples} 个交易日。分位低不等于安全边际，需结合盈利趋势。`,
              `PE percentile ${v.pePercentile?.toFixed?.(1) ?? "—"}%, PB percentile ${v.pbPercentile?.toFixed?.(1) ?? "—"}%; ${v.samples} trading days. A low percentile is not a margin of safety; pair it with earnings trends.`,
            )}
          </p>
          <button className="link-btn" onClick={() => setGlossary(true)}>{t("查术语", "Glossary")} <ChevronRight size={14} /></button>
          <div className="divider" />
          <div className="card-title-row"><h2>{t("机构观点", "Institutional view")}</h2><span className="hint">{t("机构观点 · 非 AI 判断 · 非投资建议", "Institutional view · not AI · not investment advice")}</span></div>
          {data.institutionalView?.available ? (
            <p className="muted small">{t("评级分布与目标价区间待接入。", "Rating distribution and target range are not available (no free stable source).")}</p>
          ) : (
            <p className="muted small">{data.institutionalView?.note || t("机构评级 / 目标价 / 盈利预测数据待补充", "Institutional ratings, target prices and forecasts are pending.")}</p>
          )}
          <div className="hint">{t("估值按收盘价与已披露 EPS 计算；不是一致预期。", "Valuation uses EOD price and reported EPS; not consensus estimates.")}</div>
          </>
          )}
        </section>
      )}

      {tab === "risk" && (
        <section className="card">
          <div className="card-title-row"><h2>{t("市场敏感度", "Market sensitivity")}</h2><span className="hint">{t("历史 Beta 分档", "Historical beta bucket")}</span></div>
          {data.sensitivity?.available ? (
            <div className="kpi-grid">
              <div className="kpi"><span>{t("敏感度", "Sensitivity")}</span><b>{data.sensitivity.level}</b></div>
              <div className="kpi"><span>Beta</span><b>{data.sensitivity.beta}</b></div>
            </div>
          ) : <p className="muted small">{data.sensitivity?.note || t("Beta 待补充", "Beta pending")}</p>}
          <p className="hint">{data.sensitivity?.note}</p>
          <div className="divider" />
          <div className="card-title-row"><h2>{t("风险清单", "Risk list")}</h2><span className="hint">{t("规则扫描", "Rule scan")}</span></div>
          <div className="risk-list">
            {data.risks.map((r: any, i: number) => (
              <div className="risk-item" key={i}>
                <span className={`risk-dot ${r.level}`} />
                <div><b>{r.title}</b><p>{r.detail}</p></div>
              </div>
            ))}
          </div>
          <div className="callout amber">
            <b>{t("反向观察：", "Counter-view:")}</b>
            {t("若后续毛利率企稳、成交缩量且估值分位回落，当前的部分风险标签可能被证伪。", "If margins stabilize, volume cools and valuation percentile falls, some current risk tags may be invalidated.")}
          </div>
        </section>
      )}

      <button className="news-entry" onClick={() => setNewsOpen(true)}>
        <FileText size={18} />
        <span>{isUs ? t("美股资讯：暂未接入", "US news: no free stable source") : t("个股资讯：要闻、公告、研报", "Stock news: headlines, filings, research")}</span>
        <ChevronRight size={16} />
      </button>

      <Disclaimer>{data.dataSource || t("收盘数据", "EOD data")} · {t("非实时 · 不构成投资建议", "not real-time · not investment advice")}</Disclaimer>

      <Sheet open={newsOpen} onClose={() => setNewsOpen(false)} title={t("个股资讯", "Stock news")} sub={t("标题 + 链接 · 非投资建议", "Headlines + links · not investment advice")}>
        {data.todayNews?.length ? (
          <div className="today-news">
            <b>{t("今日要闻", "Today's headlines")}</b>
            {data.todayNews.slice(0, 3).map((n: any) => (
              <a key={n.id} href={n.url} target="_blank" rel="noreferrer">{n.title}</a>
            ))}
          </div>
        ) : null}
        <div className="news-list">
          {data.news.length ? data.news.map((n: any) => (
            <div className="news-item" key={n.id}>
              <a href={n.url} target="_blank" rel="noreferrer">
                <b>{n.title}</b>
                <p>{n.summary}</p>
                <span>{n.source} · {n.published_at}</span>
              </a>
              <button
                className="btn btn-ghost btn-sm"
                disabled={annBusy === String(n.id)}
                onClick={async () => {
                  setAnnBusy(String(n.id));
                  try {
                    setAnnAi(await api("/api/invest/ai/announcement", {
                      method: "POST",
                      body: JSON.stringify({ title: n.title, summary: n.summary || "" }),
                    }));
                  } catch (e: any) {
                    toast(e.message || t("解读失败", "Summary failed"));
                  } finally {
                    setAnnBusy(null);
                  }
                }}
              >
                {annBusy === String(n.id) ? t("解读中…", "Summarizing…") : t("AI 解读", "AI summary")}
              </button>
            </div>
          )) : <div className="empty-inline">{t("暂无个股资讯。", isUs ? "US news coverage is not available (no free stable source)." : "No stock news yet.")}</div>}
        </div>
        {annAi ? <AiCard data={annAi} title={t("公告解读", "Filing summary")} /> : null}
      </Sheet>

      <Sheet open={reportOpen} onClose={() => setReportOpen(false)} title={t("财报", "Financial report")} sub={data.report ? `${data.report.period} · ${t("披露", "reported")} ${data.report.reportDate}` : t("暂无", "None")}>
        {data.report ? (
          <>
            <div className="report-grid">
              <Kv k={t("营业收入", "Revenue")} v={data.report.revenue != null ? t(`${data.report.revenue.toFixed(1)} 亿元`, `CNY ${(data.report.revenue / 100).toFixed(2)}B`) : "—"} />
              <Kv k={t("营收同比", "Revenue YoY")} v={fmtPct(data.report.revenueYoY, 1)} />
              <Kv k={t("归母净利", "Net profit")} v={data.report.netProfit != null ? t(`${data.report.netProfit.toFixed(1)} 亿元`, `CNY ${(data.report.netProfit / 100).toFixed(2)}B`) : "—"} />
              <Kv k={t("净利同比", "Profit YoY")} v={fmtPct(data.report.profitYoY, 1)} />
              <Kv k={t("毛利率", "Gross margin")} v={`${data.report.grossMargin?.toFixed?.(2)}%`} />
              <Kv k="ROE" v={`${data.report.roe?.toFixed?.(1)}%`} />
              <Kv k={t("经营现金流", "Operating cash flow")} v={data.report.ocf != null ? t(`${data.report.ocf.toFixed(1)} 亿元`, `CNY ${(data.report.ocf / 100).toFixed(2)}B`) : t("数据暂缺", "Data pending")} />
            </div>
            <div className="hint">{t("结构化财务数据；要闻、公告、研报在「个股资讯」里，两者不重复。", "Structured financials; headlines, filings and research live under Stock news and are not duplicated here.")}</div>
          </>
        ) : <div className="empty-inline">{t("暂无财报数据。", "No financial report data yet.")}</div>}
      </Sheet>

      <GlossarySheet open={glossary} onClose={() => setGlossary(false)} />
    </div>
  );
}
