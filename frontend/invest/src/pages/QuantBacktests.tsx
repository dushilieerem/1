import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { api } from "../api";
import { AiCard } from "../components/AiCard";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Sheet, Sparkline, Tag } from "../components";

type Run = {
  id: string;
  name: string;
  projectId?: string;
  finishedAt?: string;
  request?: { universe?: string };
  result?: { metrics?: Record<string, any> };
};

function pctValue(value: any): string {
  const n = Number(value);
  return Number.isFinite(n) ? `${n.toFixed(1)}%` : "待补充";
}

function numValue(value: any, digits = 2): string {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : "待补充";
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
      <PageHeader title="回测速览" sub="历史口径 · 非真实收益 · 只读网页端结果" back onBack={() => nav(-1)} />
      <div className="callout amber"><b>历史口径：</b>以下为过去区间回测，不代表未来；手机端不跑回测、不改参数、不调仓。</div>
      {error ? <ErrorState message={error} onRetry={() => setError(null)} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}
      {!loading && !runs.length ? (
        <EmptyState title="还没有回测结果" detail="在网页端跑完策略回测后，会同步到这里。" />
      ) : null}
      {runs.length ? (
        <div className="post-list">
          {runs.map((run) => {
            const m = run.result?.metrics || {};
            return (
              <button key={run.id} className="post-row" style={{ textAlign: "left" }} onClick={() => void open(run)}>
                <div className="post-row-title">{run.name || "未命名回测"}</div>
                <div className="post-row-meta">
                  <Tag tone="gray">{run.request?.universe || "—"}</Tag>
                  <span>{run.finishedAt?.slice(0, 10) || "—"}</span>
                </div>
                <div className="hint">
                  年化 {pctValue(m.annual_return)} · 最大回撤 {pctValue(m.max_drawdown)} · 夏普 {numValue(m.sharpe)}
                </div>
              </button>
            );
          })}
        </div>
      ) : null}

      <Sheet open={!!detail} onClose={() => setDetail(null)} title={detail?.name || "回测摘要"} sub="历史口径 · 非真实收益">
        {detail ? (
          <div className="backtest-detail">
            <div className="kpi-grid">
              <div className="kpi"><span>累计收益</span><b>{pctValue(metrics.cumulative_return ?? metrics.total_return)}</b></div>
              <div className="kpi"><span>年化收益</span><b>{pctValue(metrics.annual_return)}</b></div>
              <div className="kpi"><span>最大回撤</span><b>{pctValue(metrics.max_drawdown)}</b></div>
              <div className="kpi"><span>夏普</span><b>{numValue(metrics.sharpe)}</b></div>
              <div className="kpi"><span>胜率</span><b>{pctValue(metrics.win_rate)}</b></div>
              <div className="kpi"><span>波动率</span><b>{pctValue(metrics.volatility)}</b></div>
              <div className="kpi"><span>Beta</span><b>{numValue(metrics.beta)}</b></div>
              <div className="kpi"><span>Alpha</span><b>{pctValue(metrics.alpha)}</b></div>
            </div>
            {curve.length ? (
              <div className="ai-chart">
                <Sparkline values={curve} width={280} height={56} />
                <span className="hint">净值曲线 · {curve.length} 个点</span>
              </div>
            ) : <p className="hint">净值曲线待补充。</p>}
            <p className="hint">
              交易摘要：{Array.isArray(detail.result?.trades) ? `${detail.result.trades.length} 笔` : detail.result?.trade_count ?? "待补充"}；
              区间 {metrics.start_date || metrics.start || "—"} → {metrics.end_date || metrics.end || "—"}。
            </p>
            <button className="btn btn-primary btn-sm" onClick={() => void explain()} disabled={busy}>
              <Sparkles size={14} /> {busy ? "解读中…" : "AI 分析这段区间"}
            </button>
            {ai ? <AiCard data={ai} title="AI 回测解读" /> : null}
            <p className="hint">免责声明：历史收益不代表未来，非投资建议。</p>
          </div>
        ) : null}
      </Sheet>
    </div>
  );
}
