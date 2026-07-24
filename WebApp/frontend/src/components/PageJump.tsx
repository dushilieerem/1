import { useEffect, useState, type FormEvent } from "react";

/** 分页跳转：输入页码回车或点「跳转」 */
export function PageJump({
  page,
  totalPages,
  onJump,
  className = "",
}: {
  page: number;
  totalPages: number;
  onJump: (page: number) => void;
  className?: string;
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
