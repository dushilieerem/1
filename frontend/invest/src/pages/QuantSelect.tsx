import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { api } from "../api";
import { AiCard } from "../components/AiCard";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Tag } from "../components";

export default function QuantSelect() {
  const nav = useNavigate();
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
      <PageHeader title="轻量因子选股" sub="规则打分 · 不是回测，也不是推荐" back onBack={() => nav(-1)} />
      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {!data && !error ? <LoadingCards rows={3} /> : null}
      {data?.items?.length ? (
        <section className="card">
          <div className="card-title-row"><h2>按综合分排序</h2><span className="hint">{data.factors?.join(" · ")}</span></div>
          <table className="data-table">
            <thead><tr><th>标的</th><th>综合分</th><th>因子分位</th></tr></thead>
            <tbody>
              {data.items.map((it: any) => (
                <tr key={it.code}>
                  <td><button className="link-btn" onClick={() => nav(`/stock/${it.code}`)}>{it.name}</button><br /><span className="hint">{it.code}</span></td>
                  <td>{it.score}</td>
                  <td>{it.parts?.map((p: any) => `${p[0]} ${p[1]}`).join(" · ") || "待补充"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="hint">{data.note}</p>
        </section>
      ) : null}
      {!data?.items?.length && data ? <EmptyState title="暂无候选" detail="数据不足时不会给出名单。" /> : null}
      <button className="btn btn-primary btn-sm" onClick={() => void explain()} disabled={busy}>
        <Sparkles size={14} /> {busy ? "生成中…" : "AI 解释打分口径"}
      </button>
      {ai ? <AiCard data={ai} title="AI 量化解释" /> : null}
      <Tag tone="gray">历史口径 · 非真实收益</Tag>
    </div>
  );
}
