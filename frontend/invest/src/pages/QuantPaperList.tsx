import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight, Plus } from "lucide-react";
import { api } from "../api";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import { useLocale } from "../i18n";
import { fmtSignedPct, trendClass } from "../quant";

type Row = {
  id: number;
  name: string;
  strategy_name: string;
  position_count?: number | null;
  run_days?: number | null;
  cumulative?: number | null;
  today?: number | null;
  deviation?: number | null;
  status: string;
  start_date: string;
};

export default function QuantPaperList() {
  const nav = useNavigate();
  const { t } = useLocale();
  const [items, setItems] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ items: Row[] }>("/api/invest/quant/papers")
      .then((d) => setItems(d.items || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="page quant-page">
      <PageHeader
        title={t("模拟盘", "Paper trading")}
        sub={t("只做记账 · 不接券商 · 不产生真实委托", "Bookkeeping only · no broker · no real orders")}
        back
        backLabel={t("量化研究", "Quant research")}
        onBack={() => nav("/quant")}
        right={<button className="btn btn-primary btn-sm" onClick={() => nav("/quant/papers/new")}><Plus size={14} /> {t("新建", "New")}</button>}
      />
      <div className="callout amber quant-paper-warning">
        <Tag tone="amber">{t("模拟", "Simulated")}</Tag>
        <span>{t("模拟盘与真实账户无关，不显示「一键跟随」或下单入口。", "Paper accounts are separate from real accounts and show no one-click follow or order entry.")}</span>
      </div>
      {error ? <ErrorState message={error} onRetry={() => window.location.reload()} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}
      {!loading && !items.length ? (
        <EmptyState
          title={t("还没有模拟盘", "No paper accounts yet")}
          detail={t("从我的策略或草稿发起，创建后只记账。", "Create one from a tracked strategy or draft; it only records results.")}
          action={<button className="btn btn-primary btn-sm" onClick={() => nav("/quant/papers/new")}>{t("新建模拟盘", "Create paper account")}</button>}
        />
      ) : null}
      <div className="quant-paper-list">
        {items.map((item) => (
          <button className="quant-paper-row" key={item.id} onClick={() => nav(`/quant/papers/${item.id}`)}>
            <div>
              <div className="row gap6">
                <b>{item.name}</b>
                <Tag tone="amber">{t("模拟", "Simulated")}</Tag>
              </div>
              <small>
                {t(`${item.position_count ?? 0} 只持仓 · 跟随「${item.strategy_name}」 · ${item.run_days ?? 0} 天`, `${item.position_count ?? 0} positions · follows “${item.strategy_name}” · ${item.run_days ?? 0} days`)}
              </small>
            </div>
            <div className="paper-stats">
              <b className={trendClass(item.cumulative)}>{fmtSignedPct(item.cumulative)}</b>
              <small>{t("今日", "Today")} {fmtSignedPct(item.today)}</small>
            </div>
            <ChevronRight size={16} />
          </button>
        ))}
      </div>
      {items.length ? <p className="hint">{t("偏离 = 模拟盘累计收益 − 同策略同期回测累计收益。", "Deviation = paper cumulative return minus the same-period backtest return.")}</p> : null}
      <p className="quant-foot">{t("模拟成交为历史记账，不是建议，也不产生真实委托。", "Simulated fills are historical bookkeeping, not advice, and place no real orders.")}</p>
    </div>
  );
}
