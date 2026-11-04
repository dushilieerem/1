import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { api } from "../api";
import { AiCard } from "../components/AiCard";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Sheet, Sparkline, Tag } from "../components";
import { humanizeEnum } from "../lib";
import { useLocale } from "../i18n";

type Translate = (zh: string, en: string) => string;

type Run = {
  id: string;
  name: string;
  projectId?: string;
  finishedAt?: string;
  request?: { universe?: string };
  result?: { metrics?: Record<string, any> };
};

function pctValue(value: any, t: Translate): string {
  const n = Number(value);
  return Number.isFinite(n) ? `${n.toFixed(1)}%` : t("待补充", "N/A");
}

function numValue(value: any, t: Translate, digits = 2): string {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : t("待补充", "N/A");
}

function equitySeries(result: any): number[] {
  const curve = result?.equity_curve ?? result?.equity ?? [];
  if (Array.isArray(curve)) {
    return curve
      .map((x: any) => (typeof x === "number" ? x : Number(x?.equity ?? x?.value ?? x?.nav ?? x?.close)))
      .filter((x) => Number.isFinite(x));
  }
  if (curve && Array.isArray(curve.values)) {
    return curve.values.map(Number).filter((x: number) => Number.isFinite(x));
  }
  return [];
}

export default function QuantBacktests() {
  const nav = useNavigate();
  const { t } = useLocale();
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [ai, setAi] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<{ runs: Run[] }>("/api/strategy/runs")
      .then((d) => setRuns(d.runs || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const open = async (run: Run) => {
    setAi(null);
    try {
      const d = await api<{ run: any }>(`/api/strategy/runs/${run.id}`);
      setDetail(d.run);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const metrics = useMemo(() => detail?.result?.metrics || {}, [detail]);
  const curve = useMemo(() => equitySeries(detail?.result), [detail]);
  const startDate = metrics.start_date || metrics.start || "—";
  const endDate = metrics.end_date || metrics.end || "—";
  const trades = detail?.result?.trades;
  const tradeCount = Array.isArray(trades) ? trades.length : detail?.result?.trade_count;
  const tradesIsArray = Array.isArray(trades);

  const explain = async () => {
    if (!detail) return;
    setBusy(true);
    try {
      const m = metrics || {};
      setAi(await api("/api/invest/ai/backtest", {
        method: "POST",
        body: JSON.stringify({
          name: detail.name,
          universe: detail.request?.universe,
          period: { start: m.start_date || m.start, end: m.end_date || m.end },
          metrics: m,
          equity_summary: curve.length
            ? { points: curve.length, first: curve[0], last: curve[curve.length - 1] }
            : {},
          trades: Array.isArray(detail.result?.trades) ? detail.result.trades.length : detail.result?.trade_count,
        }),
      }));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <PageHeader
        title={t("回测速览", "Backtest Overview")}
        sub={t("历史口径 · 非真实收益 · 只读网页端结果", "Historical basis · not real returns · read-only web results")}
        back
        onBack={() => nav(-1)}
      />
      <div className="callout amber">
        <b>{t("历史口径：", "Historical basis: ")}</b>
        {t(
          "以下为过去区间回测，不代表未来；手机端不跑回测、不改参数、不调仓。",
          "The following are backtests over past periods and do not represent the future; mobile does not run backtests, change parameters, or rebalance.",
        )}
      </div>
      {error ? <ErrorState message={error} onRetry={() => setError(null)} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}
      {!loading && !runs.length ? (
        <EmptyState
          title={t("还没有回测结果", "No backtest results yet")}
          detail={t("在网页端跑完策略回测后，会同步到这里。", "Results will sync here after you run a strategy backtest on the web.")}
        />
      ) : null}
      {runs.length ? (
        <div className="post-list">
          {runs.map((run) => {
            const m = run.result?.metrics || {};
            return (
              <button key={run.id} className="post-row" style={{ textAlign: "left" }} onClick={() => void open(run)}>
                <div className="post-row-title">{run.name || t("未命名回测", "Unnamed backtest")}</div>
                <div className="post-row-meta">
                  <Tag tone="gray">{humanizeEnum(run.request?.universe)}</Tag>
                  <span>{run.finishedAt?.slice(0, 10) || "—"}</span>
                </div>
                <div className="hint">
                  {t("年化", "Annualized")} {pctValue(m.annual_return, t)} · {t("最大回撤", "Max drawdown")} {pctValue(m.max_drawdown, t)} · {t("夏普", "Sharpe")} {numValue(m.sharpe, t)}
                </div>
              </button>
            );
          })}
        </div>
      ) : null}

      <Sheet open={!!detail} onClose={() => setDetail(null)} title={detail?.name || t("回测摘要", "Backtest summary")} sub={t("历史口径 · 非真实收益", "Historical basis · not real returns")}>
        {detail ? (
          <div className="backtest-detail">
            <div className="kpi-grid">
              <div className="kpi"><span>{t("累计收益", "Cumulative return")}</span><b>{pctValue(metrics.cumulative_return ?? metrics.total_return, t)}</b></div>
              <div className="kpi"><span>{t("年化收益", "Annualized return")}</span><b>{pctValue(metrics.annual_return, t)}</b></div>
              <div className="kpi"><span>{t("最大回撤", "Max drawdown")}</span><b>{pctValue(metrics.max_drawdown, t)}</b></div>
              <div className="kpi"><span>{t("夏普", "Sharpe")}</span><b>{numValue(metrics.sharpe, t)}</b></div>
              <div className="kpi"><span>{t("胜率", "Win rate")}</span><b>{pctValue(metrics.win_rate, t)}</b></div>
              <div className="kpi"><span>{t("波动率", "Volatility")}</span><b>{pctValue(metrics.volatility, t)}</b></div>
              <div className="kpi"><span>Beta</span><b>{numValue(metrics.beta, t)}</b></div>
              <div className="kpi"><span>Alpha</span><b>{pctValue(metrics.alpha, t)}</b></div>
            </div>
            {curve.length ? (
              <div className="ai-chart">
                <Sparkline values={curve} width={280} height={56} />
                <span className="hint">{t(`净值曲线 · ${curve.length} 个点`, `Equity curve · ${curve.length} points`)}</span>
              </div>
            ) : <p className="hint">{t("净值曲线待补充。", "Equity curve not available yet.")}</p>}
            <p className="hint">
              {t(
                `交易摘要：${tradeCount ?? "待补充"}${tradesIsArray ? " 笔" : ""}；区间 ${startDate} → ${endDate}。`,
                `Trade summary: ${tradeCount ?? "N/A"}${tradesIsArray ? " trades" : ""}; period ${startDate} → ${endDate}.`,
              )}
            </p>
            <button className="btn btn-primary btn-sm" onClick={() => void explain()} disabled={busy}>
              <Sparkles size={14} /> {busy ? t("解读中…", "Analyzing…") : t("AI 分析这段区间", "AI: analyze this period")}
            </button>
            {ai ? <AiCard data={ai} title={t("AI 回测解读", "AI backtest commentary")} /> : null}
            <p className="hint">{t("免责声明：历史收益不代表未来，非投资建议。", "Disclaimer: past returns do not guarantee future results; not investment advice.")}</p>
          </div>
        ) : null}
      </Sheet>
    </div>
  );
}
