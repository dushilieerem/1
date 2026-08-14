import { useEffect, useState, type FormEvent } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

/** 分页跳转：输入页码回车或点「跳转」 */
export function PageJump({
  page,
  totalPages,
  onJump,
  className = "",
  /** 紧凑：仅「页码 / 总页」，适合窄屏与工具栏单行 */
  compact = false,
}: {
  page: number;
  totalPages: number;
  onJump: (page: number) => void;
  className?: string;
  compact?: boolean;
}) {
  const [draft, setDraft] = useState(String(page));

  useEffect(() => {
    setDraft(String(page));
  }, [page]);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    const n = Math.round(Number(draft));
    if (!Number.isFinite(n)) {
      setDraft(String(page));
      return;
    }
    const clamped = Math.min(totalPages, Math.max(1, n));
    setDraft(String(clamped));
    if (clamped !== page) onJump(clamped);
  };

  if (totalPages <= 1) return null;

  if (compact) {
    return (
      <form
        onSubmit={submit}
        className={`inline-flex items-center gap-1 text-xs text-slate-500 ${className}`}
      >
        <input
          type="number"
          min={1}
          max={totalPages}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => submit()}
          aria-label="跳转到页码"
          className="w-11 rounded-md border border-slate-200 bg-white px-1 py-1 text-center text-sm tabular-nums text-slate-800 outline-none focus:border-red-300 focus:ring-1 focus:ring-red-100"
        />
        <span className="shrink-0 tabular-nums text-slate-400">/ {totalPages}</span>
      </form>
    );
  }

  return (
    <form
      onSubmit={submit}
      className={`inline-flex items-center gap-1.5 text-xs text-slate-500 ${className}`}
    >
      <span className="shrink-0">跳至</span>
      <input
        type="number"
        min={1}
        max={totalPages}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => submit()}
        aria-label="跳转到页码"
        className="w-14 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-center text-sm text-slate-800 outline-none focus:border-blue-300 focus:ring-1 focus:ring-blue-200"
      />
      <span className="shrink-0">/ {totalPages} 页</span>
      <button
        type="submit"
        className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 font-medium text-slate-700 hover:bg-slate-50"
      >
        跳转
      </button>
    </form>
  );
}

/** 单行分页条：‹  页码/总页  ›（窄屏不换行） */
export function PagerBar({
  page,
  totalPages,
  onJump,
  disabled = false,
  className = "",
}: {
  page: number;
  totalPages: number;
  onJump: (page: number) => void;
  disabled?: boolean;
  className?: string;
}) {
  if (totalPages < 1) return null;

  return (
    <div
      className={`flex flex-nowrap items-center justify-center gap-2 px-2 py-2 ${className}`}
    >
      <button
        type="button"
        disabled={page <= 1 || disabled}
        onClick={() => onJump(Math.max(1, page - 1))}
        aria-label="上一页"
        className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-40"
      >
        <ChevronLeft className="h-4 w-4" />
      </button>

      {totalPages <= 1 ? (
        <span className="min-w-[4.5rem] text-center text-xs tabular-nums text-slate-500">
          1 / 1
        </span>
      ) : (
        <PageJump
          compact
          page={page}
          totalPages={totalPages}
          onJump={onJump}
          className="min-w-0"
        />
      )}

      <button
        type="button"
        disabled={page >= totalPages || disabled}
        onClick={() => onJump(Math.min(totalPages, page + 1))}
        aria-label="下一页"
        className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-40"
      >
        <ChevronRight className="h-4 w-4" />
      </button>
    </div>
  );
}
