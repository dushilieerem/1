import { lazy, Suspense, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ChevronRight, FileText, Share2, Star, TrendingDown, TrendingUp, X } from "lucide-react";
import { api } from "../api";
import { Disclaimer, ErrorState, Kv, LoadingCards, PageHeader, Sheet, Tag } from "../components";
import { fmtMoney, fmtPct, formatPrice } from "../lib";
import { useToast } from "../toast";
import GlossarySheet from "../GlossarySheet";
import AiPanel from "../components/AiPanel";

const KLineChart = lazy(() => import("../KLineChart"));

const PERIODS = [
  { key: "minute", label: "分时" },
  { key: "daily", label: "日K" },
  { key: "weekly", label: "周K" },
  { key: "monthly", label: "月K" },
];
function MinuteChart({ items }: { items: any[] }) {
  const closes = items.map((x) => Number(x.close)).filter((x) => Number.isFinite(x));
  if (!closes.length) return <div className="empty-inline">暂无有效分时价</div>;
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
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="分时走势" style={{ width: "100%", height: 170 }}>
        <polyline
          points={points}
          fill="none"
          stroke={up ? "#d14343" : "#1f9d55"}
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
      </svg>
      <div className="chart-legend">
        <span>最新 {formatPrice(last)}</span>
        <span>最高 {formatPrice(max)}</span>
        <span>最低 {formatPrice(min)}</span>
        <span>{up ? "上涨" : "下跌"} {(((last - first) / first) * 100).toFixed(2)}%</span>
      </div>
    </div>
  );
}

const TABS = [
  { key: "overview", label: "概览" },
  { key: "finance", label: "财务" },
  { key: "valuation", label: "估值" },
  { key: "risk", label: "风险" },
];

function FinancialBars({ fins }: { fins: any[] }) {
  if (!fins.length) return <div className="empty-inline">暂无财务数据</div>;
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
      <div className="hint">营业收入（亿元）· 规则展示，非预测</div>
    </div>
  );
}

export default function Stock() {
  const { code } = useParams();
  const nav = useNavigate();
  const toast = useToast();
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
    load(period);
  }, [code]);

  useEffect(() => {
    api<any>("/api/invest/watchlist")
      .then((w) => setInWatch((w.groups || []).some((g: any) => g.items.some((i: any) => i.code === code))))
      .catch(() => {});
  }, [code]);

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
    setPeriod(p);
    if (p === "minute") loadMinute();
    else load(p);
  };

  const toggleWatch = async () => {
    if (watchBusy) return;
    setWatchBusy(true);
    try {
      if (inWatch) {
        await api(`/api/invest/watchlist/${code}`, { method: "DELETE" });
        setInWatch(false);
        toast("已移出自选");
      } else {
        await api("/api/invest/watchlist", { method: "POST", body: JSON.stringify({ code }) });
        setInWatch(true);
        toast("已加入自选");
      }
    } catch (e: any) {
      toast(e.message || "操作失败");
    } finally {
      setWatchBusy(false);
    }
  };

  const share = async () => {
    try {
      await navigator.clipboard?.writeText(location.href);
      toast("链接已复制 · 含风险提示");
    } catch {
      toast("复制失败，请手动复制地址栏");
    }
  };

  if (error) {
    return (
      <div className="page">
        <PageHeader title="个股" back onBack={() => nav(-1)} />
        <ErrorState message={error} onRetry={() => load()} />
      </div>
    );
  }
  if (!data) {
    return (
      <div className="page">
        <PageHeader title="个股" back onBack={() => nav(-1)} />
        <LoadingCards rows={4} />
      </div>
    );
  }

  const q = data.quote;
  const t = data.technical;
  const v = data.valuation;
  const up = q.changePct >= 0;
  const peer = v.industryPe;
  const pct = Math.max(0, Math.min(100, v.pePercentile ?? 50));

  return (
    <div className="page stock-page">
      <PageHeader
        title={q.name}
        sub={`${q.code} · ${q.industry}`}
        back
        onBack={() => nav(-1)}
        right={
          <>
            <button className={`round-btn ${inWatch ? "active" : ""}`} onClick={toggleWatch} aria-label="自选">
              <Star size={18} fill={inWatch ? "currentColor" : "none"} />
            </button>
            <button className="round-btn" onClick={share} aria-label="分享"><Share2 size={18} /></button>
          </>
        }
      />

      <div className="topic-tags">
        <Tag tone="red">收盘数据</Tag>
        <Tag tone="gray">非实时</Tag>
        <Tag tone={data.isDemo ? "gray" : "green"}>{data.isDemo ? "演示数据" : "公开数据"}</Tag>
      </div>

      <section className="ai-summary-card">
        <div className="ai-summary-head">
          <b>数据摘要</b>
          <span>规则生成 · 非投资建议</span>
        </div>
        <ul className="fact-list">
          {data.summary.map((line: string, i: number) => <li key={i}>{line}</li>)}
        </ul>
        <button className="link-btn" onClick={() => setTab("risk")}>查看风险 <ChevronRight size={14} /></button>
      </section>

      <AiPanel
        title="AI 个股解读"
        subtitle="基于当前页面的行情、财务、估值与风险数据生成；只解释数据，不给买卖建议。"
        endpoint={`/api/invest/ai/stock/${code}`}
        buttonLabel="生成 AI 解读"
      />

      <section className="quote-card">
        <div className="quote-main">
          <div>
            <b className={up ? "up" : "down"}>{formatPrice(q.price)}</b>
            <span className={up ? "up" : "down"}>
              {up ? <TrendingUp size={14} /> : <TrendingDown size={14} />} {fmtPct(q.changePct)} · {q.change >= 0 ? "+" : ""}{q.change.toFixed(2)}
            </span>
          </div>
          <span className="quote-date">{data.dataDate} 收盘</span>
        </div>
        <div className="quote-grid">
          <div><span>最高</span><b>{formatPrice(q.high)}</b></div>
          <div><span>最低</span><b>{formatPrice(q.low)}</b></div>
          <div><span>今开</span><b>{formatPrice(q.open)}</b></div>
          <div><span>昨收</span><b>{formatPrice(q.prevClose)}</b></div>
          <div><span>流通市值</span><b>{fmtMoney(q.marketCap)}</b></div>
          <div><span>换手率</span><b>{q.turnover?.toFixed?.(2)}%</b></div>
          <div><span>成交额</span><b>{fmtMoney(q.amount)}</b></div>
          <div><span>PE(TTM)</span><b>{q.pe?.toFixed?.(2) ?? "—"}</b></div>
          <div><span>PB</span><b>{q.pb?.toFixed?.(2) ?? "—"}</b></div>
        </div>
      </section>

      <section className="card chart-card">
        <div className="card-title-row">
          <h2>行情走势</h2>
          <span className="hint">{period === "minute" ? "分时 · 非实时" : "收盘数据 · 非实时"}</span>
        </div>
        <div className="seg period-seg">
          {PERIODS.map((p) => (
            <button key={p.key} className={period === p.key ? "on" : ""} onClick={() => changePeriod(p.key)}>
              {p.label}
            </button>
          ))}
        </div>
        {period === "minute" ? (
          minuteLoading ? (
            <div className="kline-loading">加载分时…</div>
          ) : minuteError ? (
            <div className="empty-inline">分时数据不可用：{minuteError}</div>
          ) : minute?.length ? (
            <MinuteChart items={minute} />
          ) : (
            <div className="empty-inline">暂无分时数据（仅支持 2025 年以来的交易日）</div>
          )
        ) : loading ? <div className="kline-loading">加载行情…</div> : (
          <Suspense fallback={<div className="kline-loading">加载图表…</div>}>
            <KLineChart bars={data.chart.bars} ma5={data.chart.ma5} ma10={data.chart.ma10} ma20={data.chart.ma20} />
          </Suspense>
        )}
        <div className="chart-legend">
          <span><i className="legend-red" />K 线</span>
          <span><i className="legend-amber" />MA5</span>
          <span><i className="legend-purple" />MA10</span>
          <span><i className="legend-blue" />MA20</span>
        </div>
        <details className="chart-data">
          <summary>查看最近 5 根 K 线数据</summary>
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>日期</th><th>收盘</th><th>最高</th><th>最低</th></tr></thead>
              <tbody>
                {data.chart.bars.slice(-5).reverse().map((b: any) => (
                  <tr key={b.time}><td>{b.time}</td><td>{b.close}</td><td>{b.high}</td><td>{b.low}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
        <div className="hint">日/周/月 K 由收盘数据聚合；前复权口径。图表引擎：TradingView Lightweight Charts。</div>
        {code && /^(5[168]|1[56])\d{4}$/.test(code) ? (
          <Link to={`/etf/${code}`} className="link-btn" style={{ marginTop: 8, display: "inline-flex" }}>
            查看 ETF 穿透
          </Link>
        ) : null}
      </section>

      <section className="card tech-card">
        <div className="card-title-row"><h2>技术面速览</h2><span className="hint">基于日 K</span></div>
        <div className="tech-row"><span>价格趋势</span><b>{t.trend}</b><em>回撤 {fmtPct(t.drawdown, 1)} · 20 日 {fmtPct(t.return20, 1)}</em></div>
        <div className="tech-row"><span>均线系统</span><b>MA20 {t.ma20 ? formatPrice(t.ma20) : "—"}</b><em>MA5 {t.ma5 ? formatPrice(t.ma5) : "—"} · MA10 {t.ma10 ? formatPrice(t.ma10) : "—"}</em></div>
        <div className="tech-row"><span>成交量</span><b>{t.volumeRatio?.toFixed?.(1)}x</b><em>相对 20 日均量</em></div>
      </section>

      <div className="seg stock-seg">
        {TABS.map((x) => (
          <button key={x.key} className={tab === x.key ? "on" : ""} onClick={() => setTab(x.key)}>{x.label}</button>
        ))}
      </div>

      {tab === "overview" && (
        <section className="card">
          <div className="card-title-row"><h2>关键跟踪</h2><span className="hint">规则标签</span></div>
          <div className="risk-list compact">
            {data.risks.map((r: any, i: number) => (
              <div className="risk-item" key={i}>
                <span className={`risk-dot ${r.level}`} />
                <div><b>{r.title}</b><p>{r.detail}</p></div>
              </div>
            ))}
          </div>
          <div className="divider" />
          <Kv k="行业" v={q.industry} />
          <Kv k="Beta" v={q.beta?.toFixed?.(2)} />
          <Kv k="股息率" v={`${q.dividendYield?.toFixed?.(2)}%`} />
          <Kv k="下次财报（预计）" v={q.nextReportDate || "—"} />
        </section>
      )}

      {tab === "finance" && (
        <section className="card">
          <div className="card-title-row">
            <h2>财务趋势</h2>
            <button className="link-btn" onClick={() => setReportOpen(true)}>查看财报 <ChevronRight size={14} /></button>
          </div>
          {q.asset === "etf" ? <div className="empty-inline">ETF 不适用公司财务指标。</div> : (
            <>
              <FinancialBars fins={data.financials} />
              <div className="table-wrap">
                <table className="data-table">
                  <thead><tr><th>报告期</th><th>营收</th><th>同比</th><th>归母净利</th><th>毛利率</th></tr></thead>
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
              <div className="hint">单位：亿元；按报告期披露，存在滞后。</div>
            </>
          )}
        </section>
      )}

      {tab === "valuation" && (
        <section className="card">
          <div className="card-title-row"><h2>估值位置</h2><span className="hint">近 3 年历史分位</span></div>
          <div className="valuation-nums">
            <div><span>PE(TTM)</span><b>{v.pe?.toFixed?.(2) ?? "—"}x</b></div>
            <div><span>PB</span><b>{v.pb?.toFixed?.(2) ?? "—"}x</b></div>
            <div><span>行业 PE</span><b>{peer?.toFixed?.(2) ?? "—"}x</b></div>
          </div>
          <div className="valuation-track">
            <i style={{ left: `${pct}%` }} />
          </div>
          <div className="valuation-labels"><span>历史低位</span><span>当前 {v.pePercentile?.toFixed?.(1) ?? "—"}%</span><span>历史高位</span></div>
          <p className="muted small">
            PE 分位 {v.pePercentile?.toFixed?.(1) ?? "—"}%，PB 分位 {v.pbPercentile?.toFixed?.(1) ?? "—"}%；样本 {v.samples} 个交易日。
            分位低不等于安全边际，需结合盈利趋势。
          </p>
          <button className="link-btn" onClick={() => setGlossary(true)}>查术语 <ChevronRight size={14} /></button>
          <div className="hint">估值按收盘价与已披露 EPS 计算；不是一致预期。</div>
        </section>
      )}

      {tab === "risk" && (
        <section className="card">
          <div className="card-title-row"><h2>风险清单</h2><span className="hint">规则扫描</span></div>
          <div className="risk-list">
            {data.risks.map((r: any, i: number) => (
              <div className="risk-item" key={i}>
                <span className={`risk-dot ${r.level}`} />
                <div><b>{r.title}</b><p>{r.detail}</p></div>
              </div>
            ))}
          </div>
          <div className="callout amber">
            <b>反向观察：</b>若后续毛利率企稳、成交缩量且估值分位回落，当前的部分风险标签可能被证伪。
          </div>
        </section>
      )}

      <button className="news-entry" onClick={() => setNewsOpen(true)}>
        <FileText size={18} />
        <span>个股资讯：要闻、公告、研报</span>
        <ChevronRight size={16} />
      </button>

      <Disclaimer>{data.dataSource || "收盘数据"} · 非实时 · 不构成投资建议</Disclaimer>

      <div className="bottom-cta">
        <button className="btn btn-ghost" onClick={toggleWatch} disabled={watchBusy}>
          <Star size={16} fill={inWatch ? "currentColor" : "none"} /> {inWatch ? "移出自选" : "加入自选"}
        </button>
        <button className="btn btn-primary" onClick={() => nav("/portfolio")}>看组合风险 <ChevronRight size={16} /></button>
      </div>

      <Sheet open={newsOpen} onClose={() => setNewsOpen(false)} title="个股资讯" sub="标题 + 链接 · 非投资建议">
        <div className="news-list">
          {data.news.length ? data.news.map((n: any) => (
            <a className="news-item" key={n.id} href={n.url} target="_blank" rel="noreferrer">
              <b>{n.title}</b>
              <p>{n.summary}</p>
              <span>{n.source} · {n.published_at}</span>
            </a>
          )) : <div className="empty-inline">暂无个股资讯。</div>}
        </div>
      </Sheet>

      <Sheet open={reportOpen} onClose={() => setReportOpen(false)} title="财报" sub={data.report ? `${data.report.period} · 披露 ${data.report.reportDate}` : "暂无"}>
        {data.report ? (
          <>
            <div className="report-grid">
              <Kv k="营业收入" v={`${data.report.revenue?.toFixed?.(1)} 亿元`} />
              <Kv k="营收同比" v={fmtPct(data.report.revenueYoY, 1)} />
              <Kv k="归母净利" v={`${data.report.netProfit?.toFixed?.(1)} 亿元`} />
              <Kv k="净利同比" v={fmtPct(data.report.profitYoY, 1)} />
              <Kv k="毛利率" v={`${data.report.grossMargin?.toFixed?.(2)}%`} />
              <Kv k="ROE" v={`${data.report.roe?.toFixed?.(1)}%`} />
              <Kv k="经营现金流" v={data.report.ocf != null ? `${data.report.ocf.toFixed?.(1)} 亿元` : "数据暂缺"} />
            </div>
            <div className="hint">结构化财务数据；要闻、公告、研报在「个股资讯」里，两者不重复。</div>
          </>
        ) : <div className="empty-inline">暂无财报数据。</div>}
      </Sheet>

      <GlossarySheet open={glossary} onClose={() => setGlossary(false)} />
    </div>
  );
}
