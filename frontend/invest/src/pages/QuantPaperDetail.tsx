import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { api } from "../api";
import { ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import QuantChart from "../components/QuantChart";
import { useLocale } from "../i18n";
import { fmtSignedPct, metric, trendClass, type Paper } from "../quant";

type Aspect = { key: string; title: string; points: Array<{ label: string; detail: string }> };
type Commentary = { available: boolean; summary?: string; aspects?: Aspect[] };

const METRICS: Array<[string, string, string, "pct" | "num"]> = [
  ["cumulative", "累计收益", "Total return", "pct"],
  ["annual_return", "年化收益", "Annualized", "pct"],
  ["max_drawdown", "最大回撤", "Max drawdown", "pct"],
  ["sharpe", "夏普", "Sharpe", "num"],
  ["volatility", "波动率", "Volatility", "pct"],
  ["excess", "相对回测", "Vs. backtest", "pct"],
];

export default function QuantPaperDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { t, locale } = useLocale();
  const [data, setData] = useState<Paper | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ai, setAi] = useState<Commentary | null>(null);
  const [aiTried, setAiTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const aiStarted = useRef("");

  useEffect(() => {
    if (!id) return;
    api<Paper>(`/api/invest/quant/papers/${id}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [id]);

  const explain = async (refresh = false) => {
    if (!id || busy) return;
    setBusy(true);
    setAiTried(true);
    try {
      const result = await api<Commentary>(`/api/invest/quant/papers/${id}/commentary?refresh=${refresh ? 1 : 0}`, { method: "POST" });
      setAi(result.available ? result : null);
    } catch {
      setAi(null);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!data || !id) return;
    if (aiStarted.current === id) return;
    aiStarted.current = id;
    void explain(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, id]);

  return (
    <div className="page quant-page">
      <PageHeader
        title={data?.name || t("模拟盘详情", "Paper account")}
        sub={data ? `${data.start_date} · ${t("起始资金", "Starting capital")} ${(data.start_capital / 10000).toFixed(0)} 万` : undefined}
        back
        backLabel={t("量化研究", "Quant research")}
        onBack={() => nav("/quant/papers")}
      />
      {error ? <ErrorState message={error} onRetry={() => window.location.reload()} /> : null}
      {!data && !error ? <LoadingCards rows={5} /> : null}
      {data ? (
        <>
          <section className="card quant-paper-head">
            <div className="row gap6">
              <Tag tone="amber">{t("模拟", "Simulated")}</Tag>
              <span className="hint">{t("非真实账户 · 不接券商", "Not a real account · no broker")}</span>
            </div>
            <div className="quant-paper-big">
              <div><span>{t("累计收益", "Total return")}</span><b className={trendClass(data.cumulative)}>{fmtSignedPct(data.cumulative)}</b></div>
              <div><span>{t("运行天数", "Run days")}</span><b>{data.run_days ?? 0}</b></div>
            </div>
            <div className="quant-paper-meta">
              <span>{t("起始资金", "Starting capital")} <b>{data.start_capital.toLocaleString()}</b></span>
              <span>{t("相对回测偏离", "Deviation vs backtest")} <b className={trendClass(data.deviation)}>{fmtSignedPct(data.deviation)}</b></span>
              <span>{t("今日", "Today")} <b className={trendClass(data.today)}>{fmtSignedPct(data.today)}</b></span>
            </div>
          </section>

          {data.message ? <div className="callout amber">{data.message}</div> : null}

          {Object.keys(data.metrics || {}).length ? (
            <div className="kpi-grid quant-kpi-grid">
              {METRICS.map(([key, zh, en, style]) => (
                <div className="kpi" key={key}>
                  <span>{t(zh, en)}</span>
                  <b className={style === "pct" ? trendClass(data.metrics[key]) : ""}>{metric(data.metrics[key], style)}</b>
                </div>
              ))}
            </div>
          ) : null}

          {data.curve?.length ? (
            <section className="card">
              <div className="card-title-row"><h2>{t("模拟净值", "Paper NAV")}</h2><span className="hint">{t("只含记账结果", "Bookkeeping only")}</span></div>
              <QuantChart points={data.curve} showLegend={false} />
            </section>
          ) : null}

          <section className="card">
            <div className="card-title-row"><h2>{t("持仓", "Positions")}</h2><Tag tone="gray">{t("等权", "Equal weight")}</Tag></div>
            {data.positions?.length ? (
              <div className="quant-hold-list">
                {data.positions.map((p) => (
                  <button className="quant-hold-row" key={p.code} onClick={() => nav(`/stock/${p.code}`)}>
                    <div><b>{p.name}</b><span>{p.code}</span></div>
                    <div><b>{p.weight.toFixed(2)}%</b><span>{p.market_value === null ? t("市值待补充", "Value pending") : p.market_value.toLocaleString()}</span></div>
                  </button>
                ))}
              </div>
            ) : (
              <p className="hint">{t("还没有持仓，等下一次调仓。", "No positions yet; waiting for the next rebalance.")}</p>
            )}
          </section>

          <section className="card">
            <div className="card-title-row"><h2>{t("最近交易", "Recent trades")}</h2><Tag tone="gray">{t("历史记录，非建议", "History, not advice")}</Tag></div>
            {data.trades?.length ? (
              <div className="quant-trade-list">
                {data.trades.slice(-20).reverse().map((trade, i) => (
                  <div className="quant-trade-row" key={`${trade.date}-${trade.code}-${i}`}>
                    <div>
                      <b>{trade.name}</b>
                      <span>
                        {trade.date} · {trade.side === "buy" ? t("买入", "Buy") : t("卖出", "Sell")}
                        {trade.quantity ? ` · ${trade.quantity} ${t("股", "sh")}` : trade.weight_delta ? ` ${trade.weight_delta > 0 ? "+" : ""}${trade.weight_delta.toFixed(2)}%` : ""}
                        {trade.price ? ` · ${trade.price.toFixed(2)}` : ""}
                      </span>
                    </div>
                    <div>
                      <Tag tone="amber">{t("模拟成交", "Simulated")}</Tag>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="hint">{t("还没有交易记录。", "No trades yet.")}</p>
            )}
          </section>

          {!aiTried || ai ? (
          <section className="card">
            <div className="card-title-row">
              <h2>{t("AI 点评", "AI review")}</h2>
              <button className="btn btn-ghost btn-sm" onClick={() => void explain(true)} disabled={busy}>
                <Sparkles size={14} /> {busy ? t("生成中…", "Generating…") : t("重新生成", "Regenerate")}
              </button>
            </div>
            {!ai ? (
              <p className="hint">{t("自动生成 · 50 字结论 · 不满意可重新生成", "Auto-generated · 50-character takeaway · regenerate if needed")}</p>
            ) : (
              <div className="quant-ai">
                {ai.summary ? <p className="quant-ai-summary">{ai.summary}</p> : null}
                {(ai.aspects || []).map((aspect) => (
                  <div className="quant-ai-aspect" key={aspect.key}>
                    <b>{aspect.title}</b>
                    <ul>
                      {aspect.points.map((p, i) => (
                        <li key={i}><strong>{p.label}</strong>{p.detail ? `：${p.detail}` : ""}</li>
                      ))}
                    </ul>
                  </div>
                ))}
                <p className="quant-foot">{t("AI 生成 · 非投资建议", "AI-generated · not investment advice")}</p>
              </div>
            )}
          </section>
          ) : null}

          {data.factors?.length ? (
            <p className="hint">{t("跟随配置：", "Config: ")}{data.factors.map((f) => (locale === "en" ? f.name_en : f.name)).join(" · ")}</p>
          ) : null}
          <p className="quant-foot">{data.disclaimer || t("模拟盘只做记账，不接券商、不产生真实委托；历史记录，非建议。", "Paper trading is bookkeeping only, not connected to a broker and places no real orders; history, not advice.")}</p>
        </>
      ) : null}
    </div>
  );
}
