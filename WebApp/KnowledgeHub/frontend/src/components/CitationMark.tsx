import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getDocument, type KhSearchHit } from "@/lib/api";

function findHighlightContext(body: string, needle: string, radius = 220) {
  const raw = body || "";
  const n = (needle || "").trim();
  if (!raw || !n) return null;
  const norm = (s: string) => s.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const b = norm(raw);
  const t = norm(n);
  let idx = b.indexOf(t);
  let len = t.length;
  if (idx < 0) {
    const tip = t.split("\n").find((ln) => ln.trim())?.trim() || "";
    if (tip) {
      idx = b.indexOf(tip);
      len = tip.length;
    }
  }
  if (idx < 0) return null;
  const start = Math.max(0, idx - radius);
  const end = Math.min(b.length, idx + len + radius);
  return {
    before: b.slice(start, idx),
    mid: b.slice(idx, idx + len),
    after: b.slice(idx + len, end),
    clippedStart: start > 0,
    clippedEnd: end < b.length,
  };
}

export function CitationMark({
  index,
  hit,
}: {
  index: number;
  hit?: KhSearchHit;
}) {
  const [open, setOpen] = useState(false);
  const [ctx, setCtx] = useState<{
    before: string;
    mid: string;
    after: string;
    clippedStart: boolean;
    clippedEnd: boolean;
  } | null>(null);
  const [fileName, setFileName] = useState("");
  const hideTimer = useRef<number | null>(null);

  const show = () => {
    if (hideTimer.current) {
      window.clearTimeout(hideTimer.current);
      hideTimer.current = null;
    }
    setOpen(true);
  };
  const hide = () => {
    hideTimer.current = window.setTimeout(() => setOpen(false), 160);
  };

  useEffect(() => {
    if (!open || !hit) return;
    let cancelled = false;
    void getDocument(hit.documentId)
      .then((doc) => {
        if (cancelled) return;
        setFileName(doc.fileName || doc.title || "");
        const found = findHighlightContext(doc.body || "", hit.text || "");
        setCtx(found);
      })
      .catch(() => {
        if (!cancelled) setCtx(null);
      });
    return () => {
      cancelled = true;
    };
  }, [open, hit]);

  if (!hit) {
    return (
      <sup className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-slate-200 px-1 text-[10px] font-semibold text-slate-500">
        {index}
      </sup>
    );
  }

  return (
    <span
      className="relative mx-0.5 inline-block align-super"
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      <button
        type="button"
        className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-[var(--kh-teal)] px-1 text-[10px] font-bold leading-none text-white shadow-sm hover:bg-[var(--kh-teal-deep)]"
        title={`来源 #${index}`}
        aria-label={`查看引用 ${index}`}
      >
        {index}
      </button>
      {open ? (
        <div
          className="absolute left-1/2 top-[calc(100%+6px)] z-50 w-[min(420px,78vw)] -translate-x-1/2 rounded-xl border border-[var(--kh-line)] bg-white p-3 text-left shadow-xl"
          onMouseEnter={show}
          onMouseLeave={hide}
        >
          <div className="max-h-56 overflow-y-auto text-[13px] leading-relaxed text-slate-600">
            {ctx ? (
              <p className="whitespace-pre-wrap">
                {ctx.clippedStart ? "…" : ""}
                {ctx.before}
                <mark className="rounded-sm bg-transparent box-decoration-clone px-0.5 outline outline-2 outline-rose-500">
                  {ctx.mid}
                </mark>
                {ctx.after}
                {ctx.clippedEnd ? "…" : ""}
              </p>
            ) : (
              <p className="whitespace-pre-wrap">
                <mark className="rounded-sm bg-transparent box-decoration-clone px-0.5 outline outline-2 outline-rose-500">
                  {(hit.text || "").slice(0, 600)}
                  {(hit.text || "").length > 600 ? "…" : ""}
                </mark>
              </p>
            )}
          </div>
          <div className="mt-2 flex items-center gap-2 border-t border-slate-100 pt-2 text-xs text-slate-500">
            <span className="rounded bg-sky-50 px-1.5 py-0.5 font-semibold text-sky-700">
              DOC
            </span>
            <Link
              to={`/datasets/${hit.collectionId}/documents/${hit.documentId}`}
              className="truncate font-medium text-[var(--kh-teal-deep)] hover:underline"
            >
              {fileName || hit.documentTitle || `文档 #${hit.documentId}`}
            </Link>
          </div>
        </div>
      ) : null}
    </span>
  );
}
