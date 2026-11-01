import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { Disclaimer, EmptyState, ErrorState, LoadingCards, PageHeader, Tag } from "../components";

type Constituent = { symbol: string; weight: number };
type Profile = {
  etf: string;
  tracking: string;
  tracked_index: string | null;
  constituent_count?: number;
  constituents: Constituent[];
  warning?: string;
};

type Overlap = {
  a: { etf: string; tracked_index: string | null };
  b: { etf: string; tracked_index: string | null };
  common_count: number;
  overlap_weight_pct: number;
  common: Array<{ symbol: string; a: number; b: number }>;
  warning?: string;
};

export default function EtfDetail() {
  const { code = "" } = useParams();
  const nav = useNavigate();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [other, setOther] = useState("");
  const [overlap, setOverlap] = useState<Overlap | null>(null);

  useEffect(() => {
    setLoading(true);
    api<Profile>(`/api/invest/etf/${code}`)
      .then(setProfile)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [code]);

  const compare = async () => {
    if (!other.trim()) return;
    try {
      const out = await api<Overlap>(
        `/api/invest/etf/overlap?a=${encodeURIComponent(code)}&b=${encodeURIComponent(other.trim())}`,
      );
      setOverlap(out);
    } catch (e: any) {
      setError(e.message || "对比失败");
    }
  };

  return (
    <div className="page">
      <PageHeader title="ETF 穿透" sub={code} back onBack={() => nav(-1)} />
      {error ? <ErrorState message={error} onRetry={() => window.location.reload()} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}

      {!loading && profile ? (
        <>
          <section className="card">
            <div className="card-title-row">
              <h2>{profile.etf}</h2>
              <Tag tone={profile.tracking === "index_proxy" ? "amber" : "gray"}>
                {profile.tracking === "index_proxy" ? "指数代理" : "未映射"}
              </Tag>
            </div>
            <p className="hint">跟踪指数：{profile.tracked_index || "—"}</p>
            {profile.warning ? <div className="callout blue">{profile.warning}</div> : null}
          </section>

          {profile.constituents.length ? (
            <section className="card">
              <div className="card-title-row">
                <h2>成分（前 {profile.constituents.length}）</h2>
                <span className="hint">权重 %</span>
              </div>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr><th>#</th><th>代码</th><th>权重</th></tr>
                  </thead>
                  <tbody>
                    {profile.constituents.map((row, index) => (
                      <tr key={row.symbol}>
                        <td>{index + 1}</td>
                        <td>{row.symbol}</td>
                        <td>{row.weight.toFixed(3)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : (
            <EmptyState title="没有成分数据" detail="该 ETF 尚未登记跟踪指数，需要补充官方持仓或映射。" />
          )}

          <section className="card">
            <div className="card-title-row"><h2>与另一只 ETF 对比</h2></div>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                value={other}
                onChange={(e) => setOther(e.target.value)}
                placeholder="另一只 ETF，如 510500"
                style={{ flex: 1, padding: 10, borderRadius: 10, border: "1px solid var(--line)", fontSize: 13 }}
              />
              <button className="btn btn-primary" disabled={!other.trim()} onClick={compare}>
                对比
              </button>
            </div>
            {overlap ? (
              <div className="hint" style={{ marginTop: 10 }}>
                共同成分 {overlap.common_count} 只 · 加权重叠 {overlap.overlap_weight_pct.toFixed(2)}%
                {overlap.common.length ? `（${overlap.common.slice(0, 5).map((x) => x.symbol).join("、")}…）` : ""}
              </div>
            ) : null}
          </section>
        </>
      ) : null}

      <Disclaimer>代理口径：以跟踪指数成分代替 ETF 官方持仓，不构成投资建议。</Disclaimer>
    </div>
  );
}
