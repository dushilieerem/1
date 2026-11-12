import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import { fmtMoney, humanizeEnum } from "../lib";
import { useLocale } from "../i18n";

export default function QuantSignals() {
  const nav = useNavigate();
  const { t } = useLocale();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<any>("/api/invest/quant/signals")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="page">
      <PageHeader
        title={t("策略信号", "Strategy Signals")}
        sub={t("模拟盘最新持仓 · 非交易指令", "Latest paper-trading positions · not trading instructions")}
        back
        onBack={() => nav(-1)}
      />
      {error ? <ErrorState message={error} onRetry={() => window.location.reload()} /> : null}
      {!data && !error ? <LoadingCards rows={2} /> : null}
      {data && !data.accounts?.length ? (
        <EmptyState
          title={t("暂无模拟盘", "No paper accounts yet")}
          detail={t("创建模拟盘后显示策略持仓信号。", "Strategy position signals will appear after you create a paper account.")}
        />
      ) : null}
      {(data?.accounts || []).map((a: any) => (
        <section className="card" key={a.id}>
          <div className="card-title-row">
            <h2>{a.name}</h2>
            <Tag tone={a.status === "active" ? "green" : "amber"}>{humanizeEnum(a.signal)}</Tag>
          </div>
          <p className="hint">
            {a.strategyName || t("策略", "Strategy")} · {t("权益", "Equity")} {fmtMoney(a.totalEquity || 0)} · {t("现金", "Cash")} {fmtMoney(a.cash || 0)}
          </p>
          <div className="hold-list">
            {(a.positions || []).map((p: any) => (
              <div className="hold-row" key={p.symbol}>
                <div><b>{p.symbol}</b><span>{a.lastSettledDate || "—"}</span></div>
                <div className="hold-right"><b>{p.quantity}</b><span>{fmtMoney(p.marketValue || 0)}</span></div>
              </div>
            ))}
            {!(a.positions || []).length ? <div className="empty-inline">{t("空仓。", "No positions.")}</div> : null}
          </div>
        </section>
      ))}
      {data ? (
        <p className="hint">
          {t(data.note, data.note === "信号来自模拟盘最新持仓，不是实时交易指令。" ? "Signals come from the latest paper-trading positions, not live trading instructions." : data.note)}
        </p>
      ) : null}
    </div>
  );
}
