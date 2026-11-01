import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { EmptyState, ErrorState, LoadingCards, PageHeader, Tag } from "../components";

export default function QuantDashboard() {
  const nav = useNavigate();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [universe, setUniverse] = useState("CSI300");
  const [period, setPeriod] = useState("3y");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api<any>(`/api/factor/dashboard?universe=${universe}&period=${period}`)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [universe, period]);

  const rows = (data?.rows || []).slice().sort(
    (a: any, b: any) => Math.abs(Number(b.ic ?? 0)) - Math.abs(Number(a.ic ?? 0)),
  ).slice(0, 30);

  return (
    <div className="page">
      <PageHeader title="因子看板" sub="IC/IR 来自平台回测缓存 · 非预测" back onBack={() => nav(-1)} />
      <div className="seg">
        {["CSI300", "CSI500"].map((x) => (
          <button key={x} className={universe === x ? "on" : ""} onClick={() => setUniverse(x)}>{x}</button>
        ))}
        {["3m", "1y", "3y"].map((x) => (
          <button key={x} className={period === x ? "on" : ""} onClick={() => setPeriod(x)}>{x}</button>
        ))}
      </div>
      {error ? <ErrorState message={error} onRetry={() => setError(null)} /> : null}
      {loading ? <LoadingCards rows={3} /> : null}
      {!loading && !rows.length ? (
        <EmptyState title="暂无面板指标" detail="管理员刷新因子面板后会出现在这里。" />
      ) : null}
      {rows.length ? (
        <section className="card">
          <div className="card-title-row"><h2>{rows.length} 个因子</h2><span className="hint">按 |IC| 排序</span></div>
          <table className="data-table">
            <thead><tr><th>因子</th><th>IC</th><th>IR</th><th>状态</th></tr></thead>
            <tbody>
              {rows.map((r: any) => (
                <tr key={`${r.library}-${r.factor_name}`}>
                  <td>{r.factor_name}</td>
                  <td>{r.ic == null ? "待补充" : Number(r.ic).toFixed(3)}</td>
                  <td>{r.ir == null ? "待补充" : Number(r.ir).toFixed(2)}</td>
                  <td><Tag tone={r.verify_status === "passed" ? "green" : r.verify_status === "failed" ? "red" : "gray"}>{r.verify_status || "pending"}</Tag></td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="hint">IC/IR 为平台口径缓存；不构成因子推荐。</p>
        </section>
      ) : null}
    </div>
  );
}
