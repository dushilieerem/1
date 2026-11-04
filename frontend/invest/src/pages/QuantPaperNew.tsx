import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FlaskConical } from "lucide-react";
import { api } from "../api";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import { useLocale } from "../i18n";
import { factorName, fmtSignedPct, metric, trendClass, universeLabel, type Draft, type Strategy } from "../quant";

type Source = {
  key: string;
  type: "strategy" | "draft";
  id: number;
  backtest_id?: string | null;
  name: string;
  factors: Array<{ key: string; name: string; name_en: string }>;
  universe: string;
  cumulative: number | null;
  volatility: number | null;
};

export default function QuantPaperNew() {
  const nav = useNavigate();
  const { t, locale } = useLocale();
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<Source | null>(null);
  const [name, setName] = useState("");
  const [capital, setCapital] = useState("1000000");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    Promise.all([
      api<{ items: Strategy[] }>("/api/invest/quant/strategies"),
      api<{ items: Draft[] }>("/api/invest/quant/drafts"),
    ])
      .then(async ([s, d]) => {
        const list: Source[] = [];
        await Promise.all(
          (s.items || []).map(async (item) => {
            let cumulative: number | null = null;
            let volatility: number | null = null;
            if (item.backtest_id) {
              try {
                const bt = await api<any>(`/api/invest/quant/backtests/${item.backtest_id}`);
                cumulative = bt.metrics?.cumulative ?? null;
                volatility = bt.metrics?.volatility ?? null;
              } catch {
                /* 缺少回测时仍可创建，指标显示 — */
              }
            }
            list.push({
              key: `strategy-${item.id}`,
              type: "strategy",
              id: item.id,
              name: item.name,
              factors: item.factors || [],
              universe: item.universe,
              cumulative,
              volatility,
            });
          }),
        );
        await Promise.all(
          (d.items || []).map(async (item) => {
            let cumulative: number | null = null;
            let volatility: number | null = null;
            if (item.last_backtest_id) {
              try {
                const bt = await api<any>(`/api/invest/quant/backtests/${item.last_backtest_id}`);
                cumulative = bt.metrics?.cumulative ?? null;
                volatility = bt.metrics?.volatility ?? null;
              } catch {
                /* ignore */
              }
            }
            list.push({
              key: `draft-${item.id}`,
              type: "draft",
              id: item.id,
              name: item.name,
              factors: item.factors || [],
              universe: item.universe,
              cumulative,
              volatility,
            });
          }),
        );
        setSources(list);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const pick = (source: Source) => {
    setActive(source);
    setName(source.name);
  };

  const create = async () => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      const data = await api<any>("/api/invest/quant/papers", {
        method: "POST",
        body: JSON.stringify({
          source_type: active.type,
          source_id: active.id,
          name: name.trim() || active.name,
          start_capital: Number(capital) || 1000000,
        }),
      });
      nav(`/quant/papers/${data.id}`, { replace: true });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page quant-page">
      <PageHeader
        title={t("新建模拟盘", "New paper account")}
        sub={t("从我的策略或草稿发起 · 起始资金默认 100 万", "Start from a strategy or draft · default capital CNY 1m")}
        back
        backLabel={t("量化研究", "Quant research")}
        onBack={() => nav("/quant/papers")}
      />
      {error ? <ErrorState message={error} onRetry={() => setError(null)} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}
      {!loading && !sources.length ? (
        <EmptyState
          title={t("没有可发起的策略或草稿", "No strategy or draft available")}
          detail={t("先在快速实验里跑一次回测，保存草稿后就能创建模拟盘。", "Run a backtest in the quick lab and save a draft first.")}
          action={<button className="btn btn-primary btn-sm" onClick={() => nav("/quant/strategies?tab=quick")}>{t("去快速实验", "Open quick lab")}</button>}
        />
      ) : null}
      {sources.map((source) => (
        <button
          key={source.key}
          className={`quant-source-row ${active?.key === source.key ? "on" : ""}`}
          onClick={() => pick(source)}
        >
          <div>
            <div className="row gap6">
              <b>{source.name}</b>
              <Tag tone="gray">{source.type === "strategy" ? t("策略", "Strategy") : t("草稿", "Draft")}</Tag>
            </div>
            <small>
              {(source.factors || []).map((f) => factorName(f, locale)).join(" · ")} · {universeLabel(source.universe, t)}
            </small>
            <small>
              {t("回测累计", "Backtest return")} <b className={trendClass(source.cumulative)}>{fmtSignedPct(source.cumulative)}</b>
              {" · "}{t("波动", "Volatility")} {metric(source.volatility, "pct")}
            </small>
          </div>
          <span className={`quant-radio ${active?.key === source.key ? "on" : ""}`} />
        </button>
      ))}
      {active ? (
        <section className="card">
          <label className="field">
            <span>{t("模拟盘名称", "Paper account name")}</span>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder={active.name} />
          </label>
          <label className="field">
            <span>{t("起始资金", "Starting capital")}</span>
            <input value={capital} onChange={(e) => setCapital(e.target.value)} inputMode="numeric" />
          </label>
          <p className="hint">{t("运行天数从下一个交易日算；创建后不自动下单，只记账。", "Run days start from the next trading day; creating an account does not place orders, only bookkeeping.")}</p>
          <button className="btn btn-primary w100" onClick={() => void create()} disabled={busy}>
            <FlaskConical size={15} /> {busy ? t("创建中…", "Creating…") : t("创建模拟盘", "Create paper account")}
          </button>
        </section>
      ) : null}
      <p className="quant-foot">{t("模拟盘不接券商、不产生真实委托，也不构成投资建议。", "Paper accounts are not connected to a broker, place no real orders, and are not investment advice.")}</p>
    </div>
  );
}
