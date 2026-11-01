import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Sheet, Tag } from "../components";

type Strategy = {
  id: string;
  name: string;
  strategy_type?: string;
  strategy_type_label?: string;
  execution_mode?: string;
  current_version?: string;
  tags?: string[];
};

type Detail = Strategy & { strategy_code?: string };

export default function StrategyLibrary() {
  const nav = useNavigate();
  const [items, setItems] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    api<{ items: Strategy[] }>("/api/strategy/library")
      .then((d) => setItems(d.items || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return items;
    return items.filter(
      (s) =>
        s.name.toLowerCase().includes(term) ||
        (s.strategy_type_label || "").toLowerCase().includes(term) ||
        (s.tags || []).join(" ").toLowerCase().includes(term),
    );
  }, [items, q]);

  const show = async (id: string) => {
    try {
      const d = await api<Detail>(`/api/strategy/library/${encodeURIComponent(id)}`);
      setDetail(d);
      setOpen(true);
    } catch (e: any) {
      setError(e.message || "加载失败");
    }
  };

  return (
    <div className="page">
      <PageHeader title="策略库" sub={`${items.length} 个内置经典策略`} back onBack={() => nav(-1)} />
      {error ? <ErrorState message={error} onRetry={() => window.location.reload()} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}
      {!loading && !items.length ? <EmptyState title="策略库为空" detail="管理员同步后可查看。" /> : null}
      {!loading && items.length ? (
        <>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="搜索策略名称、类型或标签"
            style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid var(--line)", fontSize: 13 }}
          />
          <div className="post-list">
            {filtered.map((s) => (
              <button key={s.id} type="button" className="post-row" style={{ textAlign: "left" }} onClick={() => void show(s.id)}>
                <div className="post-row-title">{s.name}</div>
                <div className="post-row-meta">
                  <Tag tone="gray">{s.strategy_type_label || s.strategy_type}</Tag>
                  <span>{s.execution_mode}</span>
                  <span>v{s.current_version}</span>
                </div>
              </button>
            ))}
          </div>
        </>
      ) : null}

      <Sheet open={open} onClose={() => setOpen(false)} title={detail?.name || "策略"} sub={detail?.strategy_type_label}>
        <p className="hint">
          执行模式：{detail?.execution_mode} · 版本：{detail?.current_version}
        </p>
        <pre
          style={{
            marginTop: 10,
            maxHeight: 320,
            overflow: "auto",
            background: "#0f172a",
            color: "#e2e8f0",
            padding: 12,
            borderRadius: 10,
            fontSize: 11,
            lineHeight: 1.6,
          }}
        >
          {detail?.strategy_code || "（无源码快照）"}
        </pre>
      </Sheet>
    </div>
  );
}
