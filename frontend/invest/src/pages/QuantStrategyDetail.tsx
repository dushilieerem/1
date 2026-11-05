import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { FlaskConical, Play } from "lucide-react";
import { api } from "../api";
import { ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import { useLocale } from "../i18n";
import { directionLabel, factorName, fmtSignedPct, metric, supportsRePaper, trendClass, universeLabel, type Strategy } from "../quant";

export default function QuantStrategyDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { t, locale } = useLocale();
  const [data, setData] = useState<Strategy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!id) return;
    api<Strategy>(`/api/invest/quant/strategies/${id}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [id]);

  const startPaper = async () => {
    if (!data) return;
    setBusy(true);
    try {
      const created = await api<any>("/api/invest/quant/papers", {
        method: "POST",
        body: JSON.stringify({ source_type: "strategy", source_id: data.id, name: data.name }),
      });
      nav(`/quant/papers/${created.id}`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page quant-page">
      <PageHeader
        title={data?.name || t("策略详情", "Strategy details")}
        sub={data ? `${data.universe_name || universeLabel(data.universe, t)} · ${t("月度调仓", "Monthly rebalance")}` : undefined}
        back
        backLabel={t("量化研究", "Quant research")}
        onBack={() => nav("/quant/strategies?tab=mine")}
      />
      {error ? <ErrorState message={error} onRetry={() => window.location.reload()} /> : null}
      {!data && !error ? <LoadingCards rows={4} /> : null}
      {data ? (
        <>
          <section className="card">
            <div className="card-title-row">
              <h2>{t("运行状态", "Run status")}</h2>
              <Tag tone={data.status === "tracking" ? "green" : "amber"}>{locale === "en" ? data.status_label_en : data.status_label}</Tag>
            </div>
            <div className="quant-strategy-kpis">
              <div><span>{t("今日", "Today")}</span><b className={trendClass(data.today)}>{fmtSignedPct(data.today)}</b></div>
              <div><span>{t("当前回撤", "Drawdown")}</span><b>{metric(data.drawdown, "pct")}</b></div>
              <div><span>{t("偏离回测", "Deviation")}</span><b className={trendClass(data.deviation)}>{fmtSignedPct(data.deviation)}</b></div>
            </div>
            <p className="hint">{t("状态只描述系统运行，不代表买卖建议。", "Status describes system operation only, not a trading recommendation.")}</p>
          </section>

          <section className="card">
            <div className="card-title-row"><h2>{t("规则与因子", "Rules and factors")}</h2><Tag tone="gray">{t("只读", "Read-only")}</Tag></div>
            <div className="quant-rule-list">
              {(data.factors || []).map((f) => (
                <div key={f.key}>
                  <b>{factorName(f, locale)}</b>
                  <span>{directionLabel(f, (f.chosen_direction as "high" | "low") || f.direction, locale)}</span>
                  <small>{t("等权", "Equal weight")}</small>
                </div>
              ))}
            </div>
            <div className="quant-assumptions">
              <div><span>{t("股票池", "Universe")}</span><b>{data.universe_name || universeLabel(data.universe, t)}</b></div>
              <div><span>{t("持仓数", "Holdings")}</span><b>{t("前 20 只等权", "Top 20, equal weight")}</b></div>
              <div><span>{t("调仓", "Rebalance")}</span><b>{t("月度", "Monthly")}</b></div>
              <div><span>{t("成本", "Cost")}</span><b>{t("单边 0.1%", "0.1% one-way")}</b></div>
            </div>
            <p className="hint">{data.rules}</p>
          </section>

          <section className="card">
            <div className="card-title-row"><h2>{t("最近回测", "Latest backtest")}</h2>{data.backtest ? <Tag tone="green">{data.backtest.start_date} ~ {data.backtest.end_date}</Tag> : null}</div>
            {data.backtest ? (
              <>
                <div className="rounded-kpis">
                  <div><span>{t("累计", "Total")}</span><b className={trendClass(data.backtest.metrics.cumulative)}>{metric(data.backtest.metrics.cumulative, "pct")}</b></div>
                  <div><span>{t("最大回撤", "Max DD")}</span><b>{metric(data.backtest.metrics.max_drawdown, "pct")}</b></div>
                  <div><span>{t("夏普", "Sharpe")}</span><b>{metric(data.backtest.metrics.sharpe, "num")}</b></div>
                </div>
                <button className="btn btn-ghost btn-sm w100" onClick={() => nav(`/quant/backtests/${data.backtest?.id}`)}><Play size={14} /> {t("查看回测报告", "View backtest report")}</button>
              </>
            ) : (
              <p className="hint">{t("还没有关联回测。", "No linked backtest yet.")}</p>
            )}
          </section>

          <section className="card">
            <div className="card-title-row"><h2>{t("与你组合的风险对照", "Risk comparison with your portfolio")}</h2></div>
            <div className="quant-risk-compare">
              {(data.risk_compare || []).map((row) => (
                <div key={row.label}>
                  <span>{locale === "en" ? row.label_en : row.label}</span>
                  <b>{row.value ?? "—"}</b>
                </div>
              ))}
            </div>
            <p className="hint">{t("只做风险画像对照，不构成调仓建议。", "A risk-profile comparison only; not rebalancing advice.")}</p>
          </section>

          <div className="row gap6">
            {data.paper_id ? (
              <button className="btn btn-primary w100" onClick={() => nav(`/quant/papers/${data.paper_id}`)}>
                <FlaskConical size={15} /> {t("查看模拟盘", "View paper account")}
              </button>
            ) : (
              <button className="btn btn-primary w100" onClick={() => void startPaper()} disabled={busy || !supportsRePaper(data.factors)}>
                <FlaskConical size={15} /> {busy ? t("创建中…", "Creating…") : t("开模拟盘", "Start paper account")}
              </button>
            )}
            {!data.paper_id && !supportsRePaper(data.factors) ? (
              <p className="hint">{t("该策略含 ROE/营收同比等 RE 暂无字段，暂不支持模拟盘；回测记录仍可查看。", "This strategy contains ROE/revenue YoY fields not yet in RE; paper trading is unavailable, but the backtest record remains.")}</p>
            ) : null}
          </div>
          <p className="quant-foot">{t("策略状态不写「持有 / 买入 / 卖出」；历史数据不代表未来。", "Status never says hold/buy/sell; historical data does not predict the future.")}</p>
        </>
      ) : null}
    </div>
  );
}
