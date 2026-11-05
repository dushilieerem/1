import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { AiCard } from "../components/AiCard";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import { useLocale } from "../i18n";

const FACTOR_EN: Record<string, string> = {
  低估值: "Low valuation",
  高股息: "High dividend",
  "20 日动量": "20-day momentum",
};

export default function QuantSelect() {
  const nav = useNavigate();
  const { t, locale } = useLocale();
  const factorLabel = (value: string) => (locale === "en" ? FACTOR_EN[value] || value : value);
  const [data, setData] = useState<any>(null);
  const [ai, setAi] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const aiStarted = useRef(false);

  const load = () => {
    setError(null);
    api<any>("/api/invest/quant/select?top=20")
      .then(setData)
      .catch((e) => setError(e.message));
  };
  useEffect(load, []);

  const explain = async (refresh = false) => {
    setBusy(true);
    try {
      setAi(await api<any>(`/api/invest/ai/quant?refresh=${refresh ? 1 : 0}`, { method: "POST" }));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!data || aiStarted.current) return;
    aiStarted.current = true;
    void explain(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  return (
    <div className="page">
      <PageHeader
        title={t("轻量因子选股", "Lightweight Factor Screening")}
        sub={t("规则打分 · 不是回测，也不是推荐", "Rule-based scoring · not a backtest or a recommendation")}
        back
        onBack={() => nav(-1)}
      />
      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {!data && !error ? <LoadingCards rows={3} /> : null}
      {data?.items?.length ? (
        <section className="card">
          <div className="card-title-row">
            <h2>{t("按综合分排序", "Sorted by composite score")}</h2>
            <span className="hint">{data.factors?.map(factorLabel).join(" · ")}</span>
          </div>
          <table className="data-table">
            <thead><tr><th>{t("标的", "Symbol")}</th><th>{t("综合分", "Composite")}</th><th>{t("因子分位", "Factor percentile")}</th></tr></thead>
            <tbody>
              {data.items.map((it: any) => (
                <tr key={it.code}>
                  <td><button className="link-btn" onClick={() => nav(`/stock/${it.code}`)}>{it.name}</button><br /><span className="hint">{it.code}</span></td>
                  <td>{it.score}</td>
                  <td>{it.parts?.map((p: any) => `${factorLabel(p[0])} ${p[1]}`).join(" · ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="hint">
            {t(
              data.note,
              data.note === "轻量规则打分，不是策略回测，也不是推荐；缺失因子按中性处理。"
                ? "Lightweight rule-based scoring; not a backtest or recommendation. Missing factors are treated as neutral."
                : data.note,
            )}
          </p>
        </section>
      ) : null}
      {!data?.items?.length && data ? (
        <EmptyState title={t("暂无候选", "No candidates yet")} detail={t("数据不足时不会给出名单。", "No list is shown when data is insufficient.")} />
      ) : null}
      <p className="hint">{t("AI 解释自动生成 · 50 字结论 · 不满意可重新生成", "AI explanation is generated automatically · 50-character takeaway · regenerate if needed")}</p>
      {ai ? <AiCard data={ai} title={t("AI 量化解释", "AI quant commentary")} onRegenerate={() => void explain(true)} busy={busy} /> : null}
      <Tag tone="gray">{t("历史口径 · 非真实收益", "Historical basis · not real returns")}</Tag>
    </div>
  );
}
