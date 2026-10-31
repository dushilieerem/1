/** P2-04：本地草稿恢复提示。 */
export function DraftRestoreBanner({
  savedAt,
  onRestore,
  onDiscard,
}: {
  savedAt: string;
  onRestore: () => void;
  onDiscard: () => void;
}) {
  const when = (() => {
    const t = Date.parse(savedAt);
    return Number.isNaN(t) ? savedAt : new Date(t).toLocaleString("zh-CN", { hour12: false });
  })();
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
      <span className="flex-1">
        发现本地自动保存的草稿（{when}），可能比服务端更新。
      </span>
      <button
        type="button"
        onClick={onRestore}
        className="rounded-lg bg-amber-600 px-3 py-1 text-xs font-medium text-white hover:bg-amber-700"
      >
        恢复草稿
      </button>
      <button
        type="button"
        onClick={onDiscard}
        className="rounded-lg border border-amber-300 px-3 py-1 text-xs text-amber-800 hover:bg-amber-100"
      >
        丢弃
      </button>
    </div>
  );
}
