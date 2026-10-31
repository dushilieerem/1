import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Telescope } from "lucide-react";
import { instApi, fmtNum } from "@/lib/instApi";
import { useInstSession } from "@/components/institution/instSessionContext";
import { Badge, Button, Card, Empty, ErrorBox, Loading, PageHeader, StatusBadge } from "./instUi";

type Company = {
  id: number;
  symbol: string;
  name: string;
  market: string;
  industry?: string;
  ref_price?: number;
  data_status?: string;
  pool_status?: string;
  tags?: string[];
  research_points?: string[];
  pending_items?: string[];
};

const MARKETS = [
  { key: "", label: "全部市场" },
  { key: "CN", label: "A 股" },
  { key: "US", label: "美股" },
  { key: "HK", label: "港股" },
];

export function InstIdeasPage() {
  const session = useInstSession();
  const nav = useNavigate();
  const [items, setItems] = useState<Company[]>([]);
  const [market, setMarket] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canWrite = (session.permissions.ideas || "none") === "write";

  const load = () => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (market) params.set("market", market);
    if (q.trim()) params.set("q", q.trim());
    instApi<{ items: Company[] }>(`/companies?${params.toString()}`)
      .then((data) => setItems(data.items || []))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, [market]);

  const grouped = useMemo(() => {
    const order = ["CN", "US", "HK"];
    return order.map((key) => ({
      key,
      label: MARKETS.find((m) => m.key === key)?.label || key,
      items: items.filter((x) => x.market === key),
    }));
  }, [items]);

  const enterResearch = async (company: Company) => {
    if (!canWrite) return;
    setBusy(company.id);
    setError(null);
    try {
      const res = await instApi<{ id: number }>("/cases", {
        method: "POST",
        body: { company_id: company.id },
      });
      nav(`/inst/research?case=${res.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const setPool = async (company: Company, pool_status: string) => {
    if (!canWrite) return;
    setBusy(company.id);
    setError(null);
    try {
      await instApi(`/companies/${company.id}/pool`, {
        method: "POST",
        body: { pool_status, reason: pool_status === "dropped" ? "未入选：待补充研究理由" : null },
      });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="DISCOVERY / 02"
        title="机会发现"
        desc="从行业、估值与经营变化中发现研究线索；立项、观察或放弃都要保留理由。"
        actions={
          <div className="flex flex-wrap gap-2">
            {MARKETS.map((m) => (
              <button
                key={m.key || "all"}
                type="button"
                onClick={() => setMarket(m.key)}
                className={`rounded-lg border px-3 py-1.5 text-xs transition ${
                  market === m.key
                    ? "border-[#c9a15e] bg-[#fbf6ea] text-[#8a6a2f]"
                    : "border-[#e7e3d8] bg-white text-slate-600 hover:bg-[#faf8f2]"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        }
      />

      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") load();
              }}
              placeholder="输入公司名、代码或行业，回车筛选"
              className="w-full rounded-lg border border-[#dcd6c8] bg-[#faf9f5] py-2 pl-9 pr-3 text-sm outline-none focus:border-[#c9a15e]"
            />
          </div>
          <Button variant="gold" onClick={load}>
            筛选
          </Button>
          <span className="text-[11px] text-slate-400">
            共 {items.length} 个研究对象 · 当前为演示公司池
          </span>
        </div>
        {error ? <div className="mt-3"><ErrorBox message={error} onRetry={load} /></div> : null}
      </Card>

      {loading ? <Loading label="正在加载公司池…" /> : null}

      {!loading && !items.length ? (
        <Empty>
          <Telescope className="mx-auto mb-2 h-6 w-6 text-slate-300" />
          没有匹配的研究对象。换一个关键词或恢复市场筛选。
        </Empty>
      ) : null}

      {!loading &&
        grouped.map((group) =>
          group.items.length ? (
            <section key={group.key} className="space-y-3">
              <div className="flex items-center gap-2">
                <h2 className="font-display text-lg font-semibold text-slate-900">{group.label}</h2>
                <Badge>{group.items.length} 个</Badge>
              </div>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {group.items.map((c) => (
                  <article key={c.id} className="flex flex-col rounded-2xl border border-[#e7e3d8] bg-white p-5">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h3 className="font-display text-base font-semibold text-slate-900">{c.name}</h3>
                        <p className="mt-0.5 font-mono text-[11px] text-slate-500">{c.symbol}</p>
                      </div>
                      <StatusBadge status={c.data_status} />
                    </div>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      <Badge tone="gold">{c.industry || "行业待补充"}</Badge>
                      <Badge>{c.market}</Badge>
                      {c.pool_status === "watch" ? <Badge tone="amber">观察池</Badge> : null}
                      {c.pool_status === "dropped" ? <Badge tone="red">已放弃</Badge> : null}
                    </div>
                    <dl className="mt-3 space-y-1.5 text-xs text-slate-500">
                      <div className="flex justify-between gap-2">
                        <dt>参考价</dt>
                        <dd className="font-mono text-slate-800">{fmtNum(c.ref_price, 2)}</dd>
                      </div>
                      <div className="flex justify-between gap-2">
                        <dt>研究关注点</dt>
                        <dd className="max-w-[70%] text-right text-slate-700">
                          {(c.research_points || [])[0] || "待补充"}
                        </dd>
                      </div>
                    </dl>
                    <div className="mt-4 flex flex-wrap gap-2 border-t border-[#f0ece2] pt-3">
                      <Button variant="primary" disabled={!canWrite || busy === c.id} onClick={() => enterResearch(c)}>
                        {busy === c.id ? "处理中…" : "进入研究"}
                      </Button>
                      <Button variant="ghost" disabled={!canWrite || busy === c.id} onClick={() => setPool(c, "watch")}>
                        观察
                      </Button>
                      <Button variant="ghost" disabled={!canWrite || busy === c.id} onClick={() => setPool(c, "dropped")}>
                        放弃
                      </Button>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ) : null,
        )}

      <p className="text-[11px] leading-relaxed text-slate-400">
        公司池为演示研究对象；A 股研究使用真实公开行情与财务，美股/港股仅作流程占位并标注“待补充”。
        机会发现结果不是投资建议。
      </p>
    </div>
  );
}
