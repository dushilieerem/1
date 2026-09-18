import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Search } from "lucide-react";
import {
  listCollections,
  searchChunks,
  type KhCollection,
  type KhSearchHit,
} from "@/lib/api";

export function RetrievalTestPage() {
  const { id } = useParams();
  const collId = Number(id);
  const [params, setParams] = useSearchParams();
  const [coll, setColl] = useState<KhCollection | null>(null);
  const [query, setQuery] = useState(params.get("q") || "");
  const [topK, setTopK] = useState(8);
  const [hits, setHits] = useState<KhSearchHit[]>([]);
  const [meta, setMeta] = useState<{ totalCandidates: number; mode: string } | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  useEffect(() => {
    if (!collId) return;
    void listCollections()
      .then((cols) => setColl(cols.find((c) => c.id === collId) || null))
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [collId]);

  const runSearch = async (q?: string) => {
    const text = (q ?? query).trim();
    if (!text) {
      setErr("请输入查询词");
      return;
    }
    setBusy(true);
    setErr(null);
    setSearched(true);
    setParams(text ? { q: text } : {});
    try {
      const res = await searchChunks({
        query: text,
        collectionId: collId,
        topK,
      });
      setHits(res.hits || []);
      setMeta({ totalCandidates: res.totalCandidates, mode: res.mode });
    } catch (e) {
      setHits([]);
      setMeta(null);
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    const initial = params.get("q");
    if (initial?.trim() && collId) {
      void runSearch(initial);
    }
    // 仅首次带 q 时自动搜
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collId]);

  return (
    <div className="flex h-[calc(100vh-5.5rem)] flex-col overflow-hidden">
      <div className="mb-2 shrink-0 text-sm text-slate-500">
        <Link to="/datasets" className="hover:underline">
          知识库
        </Link>
        <span className="mx-1.5">›</span>
        <Link to={`/datasets/${collId}`} className="hover:underline">
          {coll?.name || `#${collId}`}
        </Link>
        <span className="mx-1.5">›</span>
        <span className="text-slate-800">检索测试</span>
      </div>

      <div className="mb-3 shrink-0">
        <h1 className="text-xl font-bold text-slate-900">检索测试</h1>
        <p className="mt-1 text-xs text-slate-400">
          当前知识库「{coll?.name || collId}」· 有向量时 hybrid（向量+关键词），否则关键词 ·
          新文档入库会自动 Embedding；旧文档请重新「解析/入库」
          后续接入
        </p>
      </div>

      <div className="mb-3 flex shrink-0 flex-wrap items-center gap-2">
        <div className="flex min-w-[240px] flex-1 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2">
          <Search className="h-4 w-4 text-slate-400" />
          <input
            className="flex-1 bg-transparent text-sm outline-none"
            placeholder="输入关键词，如 alpha101 / marketcap…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void runSearch();
            }}
          />
        </div>
        <label className="flex items-center gap-1 text-xs text-slate-500">
          TopK
          <input
            type="number"
            min={1}
            max={50}
            className="w-14 rounded border border-slate-200 px-1.5 py-1.5 text-sm"
            value={topK}
            onChange={(e) => setTopK(Number(e.target.value) || 8)}
          />
        </label>
        <button
          type="button"
          disabled={busy}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-60"
          onClick={() => void runSearch()}
        >
          {busy ? "检索中…" : "检索"}
        </button>
      </div>

      {err ? <p className="mb-2 shrink-0 text-sm text-rose-600">{err}</p> : null}

      <div className="min-h-0 flex-1 overflow-y-auto rounded-xl border border-slate-200 bg-white">
        {!searched ? (
          <p className="p-10 text-center text-sm text-slate-400">
            输入关键词后点「检索」。解析成功（ready）的文档切片才会参与。
          </p>
        ) : hits.length === 0 ? (
          <p className="p-10 text-center text-sm text-slate-400">未命中切片，换个词试试</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            <li className="bg-slate-50 px-4 py-2 text-xs text-slate-500">
              命中 {hits.length} 条
              {meta ? ` · 候选 ${meta.totalCandidates} · 模式 ${meta.mode}` : ""}
            </li>
            {hits.map((h) => (
              <li key={h.chunkId} className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
                  <span className="rounded bg-amber-50 px-1.5 py-0.5 font-mono text-amber-800">
                    score {h.score}
                  </span>
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono">
                    #{h.ordinal + 1}
                  </span>
                  <Link
                    to={`/datasets/${h.collectionId}/documents/${h.documentId}`}
                    className="text-sky-700 hover:underline"
                  >
                    {h.documentTitle}
                  </Link>
                  {typeof h.meta?.title === "string" ? (
                    <span className="truncate text-slate-500">{h.meta.title}</span>
                  ) : null}
                </div>
                <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-slate-700">
                  {h.text}
                </pre>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
