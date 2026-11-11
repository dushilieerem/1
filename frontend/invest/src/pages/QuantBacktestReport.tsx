import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ExternalLink } from "lucide-react";
import { api } from "../api";
import AiPanel from "../components/AiPanel";
import { ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import QuantChart from "../components/QuantChart";
import { useLocale } from "../i18n";
import { fmtSignedPct, metric, trendClass, universeLabel, type Backtest } from "../quant";

const METRICS: Array<[string, string, string, "pct" | "pctu" | "num" | "int"]> = [
  ["cumulative", "累计收益", "Total return", "pct"],
  ["annual_return", "年化收益", "Annualized", "pct"],
  ["max_drawdown", "最大回撤", "Max drawdown", "pct"],
  ["sharpe", "夏普", "Sharpe", "num"],
  ["win_rate", "胜率", "Win rate", "pctu"],
  ["trade_count", "交易次数", "Trades", "int"],
  ["volatility", "波动率", "Volatility", "pct"],
  ["beta", "β", "Beta", "num"],
  ["alpha", "α", "Alpha", "pct"],
];

export default function QuantBacktestReport() {
  const { id } = useParams();
  const nav = useNavigate();
  const { t, locale } = useLocale();
  const [data, setData] = useState<Backtest | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api<Backtest>(`/api/invest/quant/backtests/${id}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [id]);

  const assumptions = data?.assumptions || {};
  const assumptionRows: Array<[string, string, string]> = [
    ["universe", "股票池口径", "Universe"],
    ["rebalance", "调仓频率", "Rebalance"],
    ["holdings", "持仓数与权重", "Holdings & weights"],
    ["cost", "单边成本", "One-way cost"],
    ["dividend", "是否含分红", "Dividends"],
    ["exclusions", "剔除规则", "Exclusions"],
  ];

  return (
    <div className="page quant-page">
      <PageHeader
        title={data?.name || t("回测报告", "Backtest report")}
        sub={data ? `${data.start_date} ~ ${data.end_date}` : undefined}
        back
        backLabel={t("量化研究", "Quant research")}
        onBack={() => nav("/quant/backtests")}
        right={
          data ? (
            <button className="btn btn-ghost btn-sm" onClick={() => window.open(`/strategy?run=${data.id}`, "_blank", "noopener")}>
              <ExternalLink size={14} /> {t("完整明细", "Details")}
            </button>
          ) : undefined
        }
      />
      {error ? <ErrorState message={error} onRetry={() => window.location.reload()} /> : null}
      {!data && !error ? <LoadingCards rows={5} /> : null}
      {data ? (
        <>
          <div className="quant-factor-pills">
            {(data.factors || []).map((f) => (
              <Tag key={f.key} tone="gray">
                {locale === "en" ? f.name_en : f.name} · {f.chosen_direction === "low" ? t("低", "Low") : t("高", "High")}
              </Tag>
            ))}
            <Tag tone="blue">{universeLabel(data.universe, t)}</Tag>
            <Tag tone={data.engine === "re" ? "green" : "amber"}>{data.engine === "re" ? t("RE 回测", "RE engine") : t("本地降级", "Local fallback")}</Tag>
            {data.shortened ? <Tag tone="amber">{t("已缩短区间", "Shortened range")}</Tag> : null}
          </div>

          <div className="kpi-grid quant-report-kpis">
            {METRICS.map(([key, zh, en, style]) => (
              <div className="kpi" key={key}>
                <span>{t(zh, en)}</span>
                <b className={style === "pct" ? trendClass(data.metrics[key]) : ""}>{metric(data.metrics[key], style)}</b>
              </div>
            ))}
          </div>

          <section className="card">
            <div className="card-title-row"><h2>{t("策略与基准", "Strategy vs benchmark")}</h2><span className="hint">{t("净值归一化", "Normalized NAV")}</span></div>
            <QuantChart points={data.curve} />
            <div className="quant-bench-rows">
              <div><span>{t("基准收益", "Benchmark return")}</span><b className={trendClass(data.metrics.benchmark_return)}>{metric(data.metrics.benchmark_return, "pct")}</b></div>
              <div><span>{t("超额", "Excess")}</span><b className={trendClass(data.metrics.excess)}>{metric(data.metrics.excess, "pct")}</b></div>
            </div>
          </section>

          <section className="card">
            <div className="card-title-row"><h2>{t("回测假设", "Backtest assumptions")}</h2><Tag tone="gray">{t("固定展示", "Always shown")}</Tag></div>
            <div className="quant-assumption-grid">
              {assumptionRows.map(([key, zh, en]) => (
                <div key={key}>
                  <span>{t(zh, en)}</span>
                  <b>{String(assumptions[locale === "en" ? `${key}_en` : key] ?? assumptions[key] ?? "—")}</b>
                </div>
              ))}
            </div>
            {data.holdings?.length ? (
              <p className="hint">
                {t("最新调仓持仓：", "Latest holdings: ")}
                {data.holdings.slice(0, 8).map((h) => h.name).join("、")}
                {data.holdings.length > 8 ? t(` 等 ${data.holdings.length} 只`, ` and ${data.holdings.length} in total`) : ""}
              </p>
            ) : null}
          </section>

          <AiPanel
            title={t("AI 回测分析", "AI backtest analysis")}
            subtitle={t("按策略概述、收益、回撤、稳定性、持仓与结论六个板块解释；只引用本次回测数据。", "Six sections: strategy, returns, drawdown, stability, holdings and limitations; only this run's data.")}
            endpoint={`/api/invest/quant/backtests/${id}/commentary`}
            hideOnError
            blocksMode
            showCharts
          />

          <p className="quant-foot">{data.disclaimer || t("历史回测 · 非真实收益 · 不代表未来", "Historical backtest · not real returns · not indicative of future results")}</p>
          {data.engine !== "re" ? (
            <p className="quant-foot">
              {data.engine_reason === "unsupported_factors"
                ? t("口径说明：含 RE 暂无的基本面因子，本报告由本地数据补算。", "Basis: contains a factor not yet in RE; this report was computed locally.")
                : t("口径说明：RE 暂不可用，本报告为本地降级计算。", "Basis: RE was unavailable; this report used the local fallback.")}
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
