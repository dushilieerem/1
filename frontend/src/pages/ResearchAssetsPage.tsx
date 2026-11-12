import { useEffect, useState } from "react";
import { Database, Layers, Trash2 } from "lucide-react";
import { authHeaders } from "@/lib/auth";

type Snapshot = {
  version: string;
  content_hash: string;
  symbols?: string[];
  weights?: Record<string, number>;
  constituent_count: number;
};

type Asset = {
  id: number;
  name: string;
  description: string;
  current_version: number;
  snapshot: Snapshot;
};

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...authHeaders(), ...(init.headers || {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { detail?: string })?.detail || `HTTP ${res.status}`);
  return data as T;
}

export default function ResearchAssetsPage() {
  const [tab, setTab] = useState<"universe" | "benchmark">("universe");
  const [universes, setUniverses] = useState<Asset[]>([]);
  const [benchmarks, setBenchmarks] = useState<Asset[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [symbols, setSymbols] = useState("");
  const [weights, setWeights] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = async () => {
    try {
      const [u, b] = await Promise.all([
        call<{ items: Asset[] }>("/api/research/assets/universes"),
        call<{ items: Asset[] }>("/api/research/assets/benchmarks"),
      ]);
      setUniverses(u.items || []);
      setBenchmarks(b.items || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const submit = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      if (tab === "universe") {
        const list = symbols
          .split(/[\s,，]+/)
          .map((x) => x.trim())
          .filter(Boolean);
        await call("/api/research/assets/universes", {
          method: "POST",
          body: JSON.stringify({ name, description, symbols: list }),
        });
      } else {
        const list = weights
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean)
          .map((line) => {
            const [symbol, weight] = line.split(/[\s,，]+/);
            return { symbol, weight: Number(weight) };
          });
        await call("/api/research/assets/benchmarks", {
          method: "POST",
          body: JSON.stringify({ name, description, weights: list }),
        });
      }
      setName("");
      setDescription("");
      setSymbols("");
      setWeights("");
      setMessage("已保存（v1）");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (kind: "universes" | "benchmarks", id: number) => {
    setError(null);
    try {
      await call(`/api/research/assets/${kind}/${id}`, { method: "DELETE" });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const items = tab === "universe" ? universes : benchmarks;

  return (
    <div className="mx-auto max-w-4xl space-y-5 px-4 py-8">
      <header>
        <p className="text-[11px] tracking-[0.18em] text-red-600">RESEARCH ASSETS</p>
        <h1 className="mt-1 flex items-center gap-2 font-display text-2xl font-semibold text-slate-900">
          <Layers className="h-6 w-6 text-red-500" /> 研究资产
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          静态证券池与固定权重组合基准；每次成分变化自动生成新版本，回测结果会记录快照。
        </p>
      </header>

      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}
      {message ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{message}</div> : null}

      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setTab("universe")}
          className={`rounded-lg px-4 py-2 text-sm ${tab === "universe" ? "bg-slate-900 text-white" : "border border-slate-200 bg-white text-slate-600"}`}
        >
          证券池
        </button>
        <button
          type="button"
          onClick={() => setTab("benchmark")}
          className={`rounded-lg px-4 py-2 text-sm ${tab === "benchmark" ? "bg-slate-900 text-white" : "border border-slate-200 bg-white text-slate-600"}`}
        >
          组合基准
        </button>
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="text-sm font-semibold text-slate-800">新建{tab === "universe" ? "证券池" : "组合基准"}</h2>
        <div className="mt-3 space-y-3">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={60}
            placeholder="名称（必填）"
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
          />
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={200}
            placeholder="说明（可选）"
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
          />
          {tab === "universe" ? (
            <textarea
              value={symbols}
              onChange={(e) => setSymbols(e.target.value)}
              placeholder="证券代码，逗号或换行分隔，如 600519.SH, 000858.SZ"
              className="min-h-[110px] w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-xs"
            />
          ) : (
            <textarea
              value={weights}
              onChange={(e) => setWeights(e.target.value)}
              placeholder={"每行一个：代码 权重，如\n600519.SH 0.5\n000858.SZ 0.5"}
              className="min-h-[110px] w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-xs"
            />
          )}
          <button
            type="button"
            disabled={busy || !name.trim()}
            onClick={() => void submit()}
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
          >
            {busy ? "保存中…" : "保存"}
          </button>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="text-sm font-semibold text-slate-800">已有资产</h2>
        {items.length ? (
          <ul className="mt-3 divide-y divide-slate-100">
            {items.map((item) => (
              <li key={item.id} className="flex items-start justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-800">
                    {item.name} <span className="text-[11px] text-slate-400">v{item.current_version}</span>
                  </p>
                  <p className="mt-0.5 truncate text-xs text-slate-500">
                    {item.snapshot.symbols
                      ? item.snapshot.symbols.join(", ")
                      : Object.entries(item.snapshot.weights || {})
                          .map(([k, v]) => `${k} ${(v * 100).toFixed(1)}%`)
                          .join(", ")}
                  </p>
                  <p className="mt-0.5 font-mono text-[10px] text-slate-300">
                    hash {item.snapshot.content_hash.slice(0, 12)}…
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void remove(tab === "universe" ? "universes" : "benchmarks", item.id)}
                  className="shrink-0 rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600"
                  aria-label="删除"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 flex items-center gap-2 text-xs text-slate-400">
            <Database className="h-4 w-4" /> 还没有资产。
          </p>
        )}
      </section>
    </div>
  );
}
