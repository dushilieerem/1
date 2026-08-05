import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import {
  getDocument,
  listChunks,
  listCollections,
  type KhChunk,
  type KhCollection,
  type KhDocument,
} from "@/lib/api";

const PAGE_SIZE = 10;

type Span = { start: number; end: number };

/** 统一换行，便于 Windows 原文（\\r\\n）与切片（\\n）对齐 */
function normalizeNewlines(s: string) {
  return (s || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
}

/**
 * 在原文中定位每片范围。
 * 先按归一化换行匹配，再映射回原文下标（保留预览里的真实字符）。
 * 标题分块若用 \\n\\n 拼过多段，整段可能对不上，会退回「首行 / 标题」近似定位。
 */
function locateChunkSpans(body: string, chunks: KhChunk[]): Map<number, Span> {
  const map = new Map<number, Span>();
  if (!body) return map;

  const normToOrig: number[] = [];
  let norm = "";
  for (let i = 0; i < body.length; i++) {
    if (body[i] === "\r" && body[i + 1] === "\n") {
      normToOrig.push(i);
      norm += "\n";
      i += 1;
    } else if (body[i] === "\r") {
      normToOrig.push(i);
      norm += "\n";
    } else {
      normToOrig.push(i);
      norm += body[i];
    }
  }
  const origEnd = (normEnd: number) => {
    if (normEnd <= 0) return 0;
    if (normEnd >= normToOrig.length) return body.length;
    const last = normToOrig[normEnd - 1];
    // 若该位置是 \\r\\n 的 \\r，结束要落到 \\n 之后
    if (body[last] === "\r" && body[last + 1] === "\n") return last + 2;
    return last + 1;
  };

  let cursor = 0;
  for (const c of chunks) {
    const text = normalizeNewlines(c.text || "");
    if (!text) continue;

    let normStart = -1;
    const metaStart = c.meta?.start;
    if (typeof metaStart === "number" && metaStart >= 0 && metaStart < body.length) {
      // meta.start 是原文下标时，先估一个归一化起点再精确比
      let approx = 0;
      for (let i = 0; i < normToOrig.length; i++) {
        if (normToOrig[i] >= metaStart) {
          approx = i;
          break;
        }
      }
      const slice = norm.slice(approx, approx + text.length);
      if (slice === text || slice.startsWith(text.slice(0, Math.min(80, text.length)))) {
        normStart = approx;
      }
    }
    if (normStart < 0) normStart = norm.indexOf(text, cursor);
    if (normStart < 0) normStart = norm.indexOf(text.trim(), cursor);

    // 整段对不上时（常见于标题策略用 \\n\\n 拼接多节），用首行 / 标题近似
    if (normStart < 0) {
      const firstLine = text.split("\n").find((ln) => ln.trim())?.trim() || "";
      if (firstLine) normStart = norm.indexOf(firstLine, cursor);
    }
    if (normStart < 0) {
      const title = typeof c.meta?.title === "string" ? c.meta.title.trim() : "";
      if (title) {
        const headed = norm.indexOf(`# ${title}`, cursor);
        const headed2 = headed < 0 ? norm.indexOf(title, cursor) : headed;
        if (headed2 >= 0) normStart = headed2;
      }
    }
    if (normStart < 0) {
      const tip = text.slice(0, Math.min(80, text.length)).split("\n")[0]?.trim();
      if (tip) normStart = norm.indexOf(tip, cursor);
    }
    if (normStart < 0) normStart = norm.indexOf(text);
    if (normStart < 0) continue;

    // 若整段匹配成功用全文长度；否则高亮首段可见范围（约到下一标题或 400 字）
    let normEnd = normStart + text.length;
    const exact = norm.slice(normStart, normStart + text.length) === text;
    if (!exact) {
      const rest = norm.slice(normStart);
      const nextHeading = rest.search(/\n#{1,6}\s/);
      if (nextHeading > 0) normEnd = normStart + nextHeading;
      else normEnd = Math.min(norm.length, normStart + Math.min(text.length, 400));
    }

    const start = normToOrig[normStart] ?? 0;
    const end = origEnd(normEnd);
    map.set(c.ordinal, { start, end: Math.min(end, body.length) });
    cursor = normStart + 1;
  }
  return map;
}

export function DocumentDetailPage() {
  const { id, docId } = useParams();
  const collId = Number(id);
  const documentId = Number(docId);

  const [coll, setColl] = useState<KhCollection | null>(null);
  const [doc, setDoc] = useState<KhDocument | null>(null);
  const [chunks, setChunks] = useState<KhChunk[]>([]);
  const [q, setQ] = useState("");
  const [tab, setTab] = useState<"chunks" | "full">("chunks");
  const [activeOrdinal, setActiveOrdinal] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [err, setErr] = useState<string | null>(null);
  const previewRef = useRef<HTMLDivElement | null>(null);
  const markRef = useRef<HTMLMarkElement | null>(null);

  useEffect(() => {
    if (!collId || !documentId) return;
    void Promise.all([
      listCollections(),
      getDocument(documentId),
      listChunks(documentId),
    ])
      .then(([cols, d, ch]) => {
        setColl(cols.find((c) => c.id === collId) || null);
        setDoc(d);
        setChunks(ch);
        if (ch.length) setActiveOrdinal(ch[0].ordinal);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [collId, documentId]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return chunks;
    return chunks.filter((c) => c.text.toLowerCase().includes(needle));
  }, [chunks, q]);

  useEffect(() => {
    setPage(1);
  }, [q]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageItems = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  const spans = useMemo(
    () => locateChunkSpans(doc?.body || "", chunks),
    [doc?.body, chunks],
  );

  const active = chunks.find((c) => c.ordinal === activeOrdinal) || null;
  const activeSpan = activeOrdinal != null ? spans.get(activeOrdinal) : undefined;

  const selectChunk = (ordinal: number) => {
    setActiveOrdinal(ordinal);
    const idx = filtered.findIndex((c) => c.ordinal === ordinal);
    if (idx >= 0) setPage(Math.floor(idx / PAGE_SIZE) + 1);
  };

  useEffect(() => {
    if (!markRef.current || !previewRef.current) return;
    markRef.current.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeOrdinal, activeSpan?.start, doc?.body]);

  const bodyParts = useMemo(() => {
    const body = doc?.body || "";
    if (!body) return null;
    if (!activeSpan || activeSpan.start < 0 || activeSpan.end <= activeSpan.start) {
      return { before: body, mid: "", after: "" };
    }
    return {
      before: body.slice(0, activeSpan.start),
      mid: body.slice(activeSpan.start, activeSpan.end),
      after: body.slice(activeSpan.end),
    };
  }, [doc?.body, activeSpan]);

  if (err) {
    return <p className="text-sm text-rose-600">{err}</p>;
  }
  if (!doc) {
    return <p className="text-slate-500">加载中…</p>;
  }

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
        <span className="text-slate-800">{doc.title}</span>
      </div>

      <div className="mb-2 shrink-0">
        <h1 className="text-xl font-bold text-slate-900">{doc.title}</h1>
        <p className="mt-1 text-xs text-slate-400">
          状态 {doc.status} · 分块 {doc.chunkStrategy || coll?.chunkStrategy || "—"} ·{" "}
          {chunks.length} 片
          {doc.fileSize ? ` · ${doc.fileSize} B` : ""}
          {doc.createdAt ? ` · ${doc.createdAt.slice(0, 19)}` : ""}
        </p>
      </div>

      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-2">
        <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white">
          <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-4 py-2.5">
            <span className="text-sm font-medium text-slate-700">原文预览</span>
            {active ? (
              <span className="text-xs text-amber-700">
                {activeSpan
                  ? `已高亮切片 #${active.ordinal + 1}`
                  : `切片 #${active.ordinal + 1} 无法在原文精确定位（多段拼接或换行差异），不影响检索`}
              </span>
            ) : null}
          </div>
          <div
            ref={previewRef}
            className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden whitespace-pre-wrap break-words p-4 font-sans text-sm leading-relaxed text-slate-700"
          >
            {bodyParts ? (
              <>
                {bodyParts.before}
                {bodyParts.mid ? (
                  <mark
                    ref={markRef}
                    className="rounded-sm bg-amber-200/90 text-slate-900 ring-2 ring-amber-400/60"
                  >
                    {bodyParts.mid}
                  </mark>
                ) : null}
                {bodyParts.after}
              </>
            ) : (
              "（无正文）"
            )}
          </div>
        </section>

        <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white">
          <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-2.5">
            <div>
              <p className="text-sm font-medium text-slate-700">切片结果</p>
              <p className="text-xs text-slate-400">查看用于导入和召回的切片列表</p>
            </div>
            <div className="ml-auto flex items-center gap-1 rounded-lg bg-slate-100 p-0.5 text-xs">
              <button
                type="button"
                className={`rounded-md px-2.5 py-1 ${tab === "full" ? "bg-white shadow-sm" : "text-slate-500"}`}
                onClick={() => setTab("full")}
              >
                全文
              </button>
              <button
                type="button"
                className={`rounded-md px-2.5 py-1 ${tab === "chunks" ? "bg-white shadow-sm" : "text-slate-500"}`}
                onClick={() => setTab("chunks")}
              >
                结果
              </button>
            </div>
          </div>

          {tab === "chunks" ? (
            <>
              <div className="flex shrink-0 items-center gap-2 border-b border-slate-50 px-3 py-2">
                <Search className="h-4 w-4 text-slate-400" />
                <input
                  className="flex-1 bg-transparent text-sm outline-none"
                  placeholder="在切片中搜索…"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
                <span className="text-xs text-slate-400">共 {filtered.length} 条</span>
              </div>
              <ul className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
                {pageItems.length === 0 ? (
                  <li className="py-10 text-center text-sm text-slate-400">暂无切片</li>
                ) : (
                  pageItems.map((c) => {
                    const title =
                      typeof c.meta?.title === "string" ? c.meta.title : null;
                    const activeRow = c.ordinal === activeOrdinal;
                    return (
                      <li key={c.id}>
                        <button
                          type="button"
                          onClick={() => selectChunk(c.ordinal)}
                          className={`w-full rounded-lg border px-3 py-2.5 text-left transition ${
                            activeRow
                              ? "border-sky-300 bg-sky-50/80"
                              : "border-slate-200 hover:border-slate-300"
                          }`}
                        >
                          <div className="mb-1 flex items-center gap-2 text-xs text-slate-400">
                            <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-slate-600">
                              #{c.ordinal + 1}
                            </span>
                            {title ? <span className="truncate">{title}</span> : null}
                            <span className="ml-auto">{c.text.length} 字</span>
                          </div>
                          <p className="line-clamp-4 whitespace-pre-wrap text-sm text-slate-700">
                            {c.text}
                          </p>
                        </button>
                      </li>
                    );
                  })
                )}
              </ul>
              <div className="flex shrink-0 items-center justify-between gap-2 border-t border-slate-100 px-3 py-2 text-sm">
                <button
                  type="button"
                  className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 disabled:opacity-40"
                  disabled={safePage <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  <ChevronLeft className="h-4 w-4" />
                  上一页
                </button>
                <span className="text-xs text-slate-500">
                  第 {safePage} / {totalPages} 页 · 每页 {PAGE_SIZE} 条
                </span>
                <button
                  type="button"
                  className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 disabled:opacity-40"
                  disabled={safePage >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                >
                  下一页
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </>
          ) : (
            <div className="min-h-0 flex-1 overflow-y-auto p-4">
              {active ? (
                <>
                  <p className="mb-2 text-xs text-slate-400">
                    当前切片 #{active.ordinal + 1}
                    {typeof active.meta?.title === "string"
                      ? ` · ${active.meta.title}`
                      : ""}
                  </p>
                  <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-slate-700">
                    {active.text}
                  </pre>
                </>
              ) : (
                <p className="text-sm text-slate-400">请先在「结果」中选择一条切片</p>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
