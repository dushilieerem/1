import { useEffect, useState } from "react";

type MinuteBar = {
  time: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  amount: number | null;
};

/** P1-D02：分钟线查询结果（表格形式，避免与日线图表时间轴混用）。 */
export function MinuteBarsPanel({ symbol }: { symbol: string }) {
  const [rows, setRows] = useState<MinuteBar[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setNote(null);
    fetch(
      `/api/market-data/minute/${encodeURIComponent(symbol)}?limit_days=1`,
      { cache: "no-store" },
    )
      .then(async (res) => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
        if (cancelled) return;
        setRows((data.items || []) as MinuteBar[]);
        if (!(data.items || []).length) {
          setNote(data.note || "当前区间没有分钟数据");
        }
      })
      .catch((e) => {
        if (!cancelled) setNote(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  const shown = expanded ? rows : rows.slice(-30);

  return (
    <section className="mt-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-bold text-slate-900">1 分钟行情</h2>
          <p className="mt-0.5 text-xs text-slate-400">
            最近交易日 · 数据来自本地 marketdata release
          </p>
        </div>
        {rows.length > 30 && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="shrink-0 rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50"
          >
            {expanded ? "只看最近 30 条" : `展开全部 ${rows.length} 条`}
          </button>
        )}
      </div>
      {loading ? (
        <p className="py-6 text-center text-sm text-slate-400">加载分钟线…</p>
      ) : note ? (
        <p className="py-4 text-sm text-amber-700">{note}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-right text-xs tabular-nums">
            <thead className="text-slate-400">
              <tr className="border-b border-slate-100">
                {["时间", "开", "高", "低", "收", "成交量", "成交额"].map((h) => (
                  <th key={h} className="whitespace-nowrap px-2 py-1.5 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((b) => (
                <tr key={b.time} className="border-b border-slate-50 text-slate-700">
                  <td className="whitespace-nowrap px-2 py-1 text-slate-500">
                    {b.time.slice(11, 16)}
                  </td>
                  <td className="px-2 py-1">{fmt(b.open)}</td>
                  <td className="px-2 py-1">{fmt(b.high)}</td>
                  <td className="px-2 py-1">{fmt(b.low)}</td>
                  <td
                    className={`px-2 py-1 font-medium ${
                      b.close != null && b.open != null && b.close >= b.open
                        ? "text-rose-600"
                        : "text-emerald-600"
                    }`}
                  >
                    {fmt(b.close)}
                  </td>
                  <td className="px-2 py-1">{fmtVol(b.volume)}</td>
                  <td className="px-2 py-1">{fmtVol(b.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function fmt(v: number | null): string {
  return v == null ? "—" : v.toFixed(2);
}

function fmtVol(v: number | null): string {
  if (v == null) return "—";
  if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(2)}亿`;
  if (Math.abs(v) >= 1e4) return `${(v / 1e4).toFixed(1)}万`;
  return v.toFixed(0);
}
