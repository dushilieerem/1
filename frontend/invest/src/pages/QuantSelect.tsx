import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { api } from "../api";
import { AiCard } from "../components/AiCard";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import { useLocale } from "../i18n";

export default function QuantSelect() {
  const nav = useNavigate();
  const { t } = useLocale();
  const [data, setData] = useState<any>(null);
  const [ai, setAi] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    api<any>("/api/invest/quant/select?top=20")
      .then(setData)
      .catch((e) => setError(e.message));
  };
  useEffect(load, []);

  const explain = async () => {
    setBusy(true);
    try {
      setAi(await api<any>("/api/invest/ai/quant", { method: "POST" }));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

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
            <span className="hint">{data.factors?.join(" · ")}</span>
          </div>
          <table className="data-table">
            <thead><tr><th>{t("标的", "Symbol")}</th><th>{t("综合分", "Composite")}</th><th>{t("因子分位", "Factor percentile")}</th></tr></thead>
            <tbody>
              {data.items.map((it: any) => (
                <tr key={it.code}>
                  <td><button className="link-btn" onClick={() => nav(`/stock/${it.code}`)}>{it.name}</button><br /><span className="hint">{it.code}</span></td>
                  <td>{it.score}</td>
                  <td>{it.parts?.map((p: any) => `${p[0]} ${p[1]}`).join(" · ") || t("待补充", "N/A")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="hint">{data.note}</p>
        </section>
      ) : null}
      {!data?.items?.length && data ? (
        <EmptyState title={t("暂无候选", "No candidates yet")} detail={t("数据不足时不会给出名单。", "No list is shown when data is insufficient.")} />
      ) : null}
      <button className="btn btn-primary btn-sm" onClick={() => void explain()} disabled={busy}>
        <Sparkles size={14} /> {busy ? t("生成中…", "Generating…") : t("AI 解释打分口径", "AI: explain scoring method")}
      </button>
      {ai ? <AiCard data={ai} title={t("AI 量化解释", "AI quant commentary")} /> : null}
      <Tag tone="gray">{t("历史口径 · 非真实收益", "Historical basis · not real returns")}</Tag>
    </div>
  );
}
