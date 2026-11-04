import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight, Plus } from "lucide-react";
import { api } from "../api";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import { useLocale } from "../i18n";
import { fmtSignedPct, trendClass, universeLabel } from "../quant";

type Row = {
  id: string;
  name: string;
  factors: Array<{ name: string; name_en: string }>;
  universe: string;
  range: string;
  cumulative: number | null;
  benchmark_return: number | null;
  shortened: boolean;
  created_at?: string;
};

export default function QuantBacktestList() {
  const nav = useNavigate();
  const { t, locale } = useLocale();
  const [items, setItems] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ items: Row[] }>("/api/invest/quant/backtests")
      .then((d) => setItems(d.items || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="page quant-page">
      <PageHeader
        title={t("回测", "Backtests")}
        sub={t("我跑过哪些回测 · 不同区间不做横向比较", "Your backtest records · ranges are not compared side by side")}
        back
        backLabel={t("量化研究", "Quant research")}
        onBack={() => nav("/quant")}
        right={<button className="btn btn-primary btn-sm" onClick={() => nav("/quant/strategies?tab=quick")}><Plus size={14} /> {t("新建回测", "New")}</button>}
      />
      {error ? <ErrorState message={error} onRetry={() => window.location.reload()} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}
      {!loading && !items.length ? (
        <EmptyState
          title={t("还没有回测记录", "No backtest records yet")}
          detail={t("在策略页的快速实验里跑一次，结果会自动保存在这里。", "Run the quick lab on the strategy page and results will be saved here.")}
          action={<button className="btn btn-primary btn-sm" onClick={() => nav("/quant/strategies?tab=quick")}>{t("去快速实验", "Open quick lab")}</button>}
        />
      ) : null}
      <div className="quant-backtest-list">
        {items.map((item) => (
          <button className="quant-backtest-row" key={item.id} onClick={() => nav(`/quant/backtests/${item.id}`)}>
            <div className="backtest-main">
              <b>{item.name}</b>
              <small>
                {item.range} · {universeLabel(item.universe, t)} · {t("月度调仓", "Monthly rebalance")}
                {item.shortened ? ` · ${t("已缩短区间", "Shortened")}` : ""}
              </small>
            </div>
            <div className="backtest-stats">
              <b className={trendClass(item.cumulative)}>{fmtSignedPct(item.cumulative)}</b>
              <small>{t("基准", "Benchmark")} {fmtSignedPct(item.benchmark_return)}</small>
            </div>
            <ChevronRight size={16} />
          </button>
        ))}
      </div>
      {items.length ? <Tag tone="gray">{t("记录按创建时间排列，不按收益排序。", "Records are ordered by creation time, not return.")}</Tag> : null}
      <p className="quant-foot">{t("历史回测 · 非真实收益 · 不代表未来。", "Historical backtest · not real returns · not indicative of future results.")}</p>
    </div>
  );
}
