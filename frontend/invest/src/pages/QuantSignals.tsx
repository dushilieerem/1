import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import { fmtMoney } from "../lib";

export default function QuantSignals() {
  const nav = useNavigate();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<any>("/api/invest/quant/signals")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="page">
      <PageHeader title="策略信号" sub="模拟盘最新持仓 · 非交易指令" back onBack={() => nav(-1)} />
      {error ? <ErrorState message={error} onRetry={() => window.location.reload()} /> : null}
      {!data && !error ? <LoadingCards rows={2} /> : null}
      {data && !data.accounts?.length ? <EmptyState title="暂无模拟盘" detail="创建模拟盘后显示策略持仓信号。" /> : null}
      {(data?.accounts || []).map((a: any) => (
        <section className="card" key={a.id}>
          <div className="card-title-row">
            <h2>{a.name}</h2>
            <Tag tone={a.status === "active" ? "green" : "amber"}>{a.signal}</Tag>
          </div>
          <p className="hint">{a.strategyName || "策略"} · 权益 {fmtMoney(a.totalEquity || 0)} · 现金 {fmtMoney(a.cash || 0)}</p>
          <div className="hold-list">
            {(a.positions || []).map((p: any) => (
              <div className="hold-row" key={p.symbol}>
                <div><b>{p.symbol}</b><span>{a.lastSettledDate || "—"}</span></div>
                <div className="hold-right"><b>{p.quantity}</b><span>{fmtMoney(p.marketValue || 0)}</span></div>
              </div>
            ))}
            {!(a.positions || []).length ? <div className="empty-inline">空仓。</div> : null}
          </div>
        </section>
      ))}
      {data ? <p className="hint">{data.note}</p> : null}
    </div>
  );
}
