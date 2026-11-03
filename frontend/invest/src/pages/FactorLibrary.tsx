import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Tag } from "../components";
import { useLocale } from "../i18n";

type Library = { id: number; name: string; factor_count?: number };
type Factor = { id: number; name: string; description?: string; library_name?: string; category?: string };

export default function FactorLibrary() {
  const nav = useNavigate();
  const { t } = useLocale();
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
      <PageHeader
        title={t("因子库", "Factor Library")}
        sub={t(`${factors.length} 个已入库因子`, `${factors.length} registered factors`)}
        back
        onBack={() => nav(-1)}
      />
      {error ? <ErrorState message={error} onRetry={() => window.location.reload()} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}
      {!loading && !factors.length ? (
        <EmptyState
          title={t("还没有因子", "No factors yet")}
          detail={t("在桌面端因子检测后入库，会同步到这里。", "Factors registered after desktop factor checks will sync here.")}
        />
      ) : null}
      {!loading && factors.length ? (
        <>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("搜索因子名称或说明", "Search factor name or description")}
            style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid var(--line)", fontSize: 13 }}
          />
          <p className="hint" style={{ marginTop: 8 }}>
            {t("因子库：", "Libraries: ")}{libraries.map((l) => l.name).join(t("、", ", ")) || "—"}
          </p>
          <div className="post-list">
            {filtered.map((f) => (
              <div key={f.id} className="post-row">
                <div className="post-row-title">{f.name}</div>
                <div className="post-row-meta">
                  <Tag tone="gray">{f.library_name || t("自定义", "Custom")}</Tag>
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
