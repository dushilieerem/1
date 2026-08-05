import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Pencil, Plus, Trash2 } from "lucide-react";
import {
  createCollection,
  deleteCollection,
  listCollections,
  updateCollection,
  type KhCollection,
} from "@/lib/api";
import { ConfirmModal, ModalShell, NamePromptModal } from "@/components/Modals";

export function DatasetsPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<KhCollection[]>([]);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<KhCollection | null>(null);
  const [pendingRename, setPendingRename] = useState<KhCollection | null>(null);

  const reload = () =>
    listCollections().then(setItems).catch((e) => setErr(String(e.message || e)));

  useEffect(() => {
    void reload();
  }, []);

  const onCreate = async () => {
    if (!name.trim()) return;
    try {
      const c = await createCollection({
        name: name.trim(),
      });
      setOpen(false);
      setName("");
      await reload();
      navigate(`/datasets/${c.id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="pb-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="kh-display text-2xl font-bold text-[var(--kh-ink)]">知识库</h1>
          <p className="mt-1 text-sm text-slate-500">文档入库 · 切片 · 向量检索</p>
        </div>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="kh-btn-primary inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-sm font-medium"
        >
          <Plus className="h-4 w-4" />
          创建知识库
        </button>
      </div>
      {err ? <p className="mt-3 text-sm text-rose-600">{err}</p> : null}

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {items.map((c, i) => (
          <div
            key={c.id}
            className="kh-card kh-card-kb group relative min-h-[140px] p-5 kh-fade-in"
            style={{ animationDelay: `${i * 40}ms` }}
          >
            <Link to={`/datasets/${c.id}`} className="block pr-16">
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--kh-cyan)] to-[var(--kh-teal-deep)] text-sm font-bold text-white">
                {c.name.slice(0, 1).toUpperCase()}
              </div>
              <p className="font-semibold text-[var(--kh-ink)]">{c.name}</p>
              <p className="mt-1 text-xs text-slate-500">{c.documentCount} 个文件</p>
            </Link>
            <div className="absolute right-2 top-2 flex gap-0.5 opacity-0 group-hover:opacity-100">
              <button
                type="button"
                title="重命名"
                className="rounded-lg p-1 text-slate-400 hover:bg-teal-50 hover:text-[var(--kh-teal-deep)]"
                onClick={() => setPendingRename(c)}
              >
                <Pencil className="h-4 w-4" />
              </button>
              <button
                type="button"
                title="删除"
                className="rounded-lg p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                onClick={() => setPendingDelete(c)}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {open ? (
        <ModalShell title="创建知识库" onClose={() => setOpen(false)}>
          <label className="block text-xs text-slate-500">名称</label>
          <input
            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="请输入名称"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") void onCreate();
            }}
          />
          <p className="mt-2 text-xs text-slate-400">
            分块方法在上传文档时选择，同一知识库内不同文件可用不同策略。
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button
              type="button"
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
              onClick={() => setOpen(false)}
            >
              取消
            </button>
            <button
              type="button"
              className="kh-btn-primary rounded-lg px-3 py-2 text-sm"
              onClick={() => void onCreate()}
            >
              保存
            </button>
          </div>
        </ModalShell>
      ) : null}

      {pendingRename ? (
        <NamePromptModal
          title="重命名知识库"
          label="名称"
          defaultValue={pendingRename.name}
          onCancel={() => setPendingRename(null)}
          onConfirm={(v) => {
            const id = pendingRename.id;
            setPendingRename(null);
            void updateCollection(id, { name: v })
              .then(reload)
              .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
          }}
        />
      ) : null}

      {pendingDelete ? (
        <ConfirmModal
          title="删除知识库"
          message={`确定删除知识库「${pendingDelete.name}」？此操作不可恢复。`}
          confirmText="删除"
          danger
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => {
            const id = pendingDelete.id;
            setPendingDelete(null);
            void deleteCollection(id).then(reload);
          }}
        />
      ) : null}
    </div>
  );
}
