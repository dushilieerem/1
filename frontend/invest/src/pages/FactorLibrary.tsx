import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Tag } from "../components";

type Library = { id: number; name: string; factor_count?: number };
type Factor = { id: number; name: string; description?: string; library_name?: string; category?: string };

export default function FactorLibrary() {
  const nav = useNavigate();
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [factors, setFactors] = useState<Factor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    Promise.all([
      api<{ libraries: Library[] }>("/api/factor/libraries"),
      api<{ factors: Factor[] }>("/api/factor/libraries/factors"),
    ])
      .then(([l, f]) => {
        setLibraries(l.libraries || []);
        setFactors(f.factors || []);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return factors;
    return factors.filter(
      (f) => f.name.toLowerCase().includes(term) || (f.description || "").toLowerCase().includes(term),
    );
  }, [factors, q]);

  return (
    <div className="page">
      <PageHeader title="因子库" sub={`${factors.length} 个已入库因子`} back onBack={() => nav(-1)} />
      {error ? <ErrorState message={error} onRetry={() => window.location.reload()} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}
      {!loading && !factors.length ? (
        <EmptyState title="还没有因子" detail="在桌面端因子检测后入库，会同步到这里。" />
      ) : null}
      {!loading && factors.length ? (
        <>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="搜索因子名称或说明"
            style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid var(--line)", fontSize: 13 }}
          />
          <p className="hint" style={{ marginTop: 8 }}>
            因子库：{libraries.map((l) => l.name).join("、") || "—"}
          </p>
          <div className="post-list">
            {filtered.map((f) => (
              <div key={f.id} className="post-row">
                <div className="post-row-title">{f.name}</div>
                <div className="post-row-meta">
                  <Tag tone="gray">{f.library_name || "自定义"}</Tag>
                  {f.category ? <span>{f.category}</span> : null}
                </div>
                {f.description ? <div className="hint">{f.description}</div> : null}
              </div>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
