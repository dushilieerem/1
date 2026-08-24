import { useEffect, useRef, useState } from "react";
import { Plus, Search } from "lucide-react";
import { createFile, deleteFile, listCollections, listFiles, type KhCollection, type KhFile } from "@/lib/api";
import { ConfirmModal } from "@/components/Modals";

export function FilesPage() {
  const [files, setFiles] = useState<KhFile[]>([]);
  const [collections, setCollections] = useState<KhCollection[]>([]);
  const [q, setQ] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const reload = () =>
    Promise.all([listFiles(), listCollections()]).then(([f, c]) => {
      setFiles(f);
      setCollections(c);
    });

  useEffect(() => {
    void reload().catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  const onPick = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      void createFile({
        title: file.name.replace(/\.(md|txt)$/i, ""),
        fileName: file.name,
        body: String(reader.result || ""),
        collectionId: collections[0]?.id ?? null,
      })
        .then(() => reload())
        .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
    };
    reader.readAsText(file, "utf-8");
  };

  const filtered = files.filter(
    (f) => !q.trim() || f.title.includes(q) || f.fileName.includes(q),
  );

  return (
    <div className="pb-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="kh-display text-2xl font-bold text-[var(--kh-ink)]">文件</h1>
          <p className="mt-1 text-sm text-slate-500">上传与登记，可关联到知识库</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 rounded-xl border border-[var(--kh-line)] bg-white/90 px-2 py-1.5">
            <Search className="h-4 w-4 text-slate-400" />
            <input
              className="w-40 bg-transparent text-sm outline-none"
              placeholder="搜索"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".md,.txt,text/plain,text/markdown"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onPick(f);
              e.target.value = "";
            }}
          />
          <button
            type="button"
            className="kh-btn-primary inline-flex items-center gap-1 rounded-xl px-3 py-2 text-sm"
            onClick={() => fileRef.current?.click()}
          >
            <Plus className="h-4 w-4" />
            新增文件
          </button>
        </div>
      </div>
      {err ? <p className="mt-3 text-sm text-rose-600">{err}</p> : null}

      <div className="kh-panel mt-6 overflow-hidden rounded-2xl">
        <table className="w-full text-left text-sm">
          <thead className="bg-[var(--kh-mist)]/70 text-xs text-slate-500">
            <tr>
              <th className="px-4 py-3 font-medium">名称</th>
              <th className="px-4 py-3 font-medium">上传日期</th>
              <th className="px-4 py-3 font-medium">大小</th>
              <th className="px-4 py-3 font-medium">知识库</th>
              <th className="px-4 py-3 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-slate-400">
                  未查询到相关结果
                </td>
              </tr>
            ) : (
              filtered.map((f) => (
                <tr key={f.id} className="border-t border-[var(--kh-line)]">
                  <td className="px-4 py-3 font-medium text-slate-800">{f.title}</td>
                  <td className="px-4 py-3 text-slate-500">{f.createdAt?.slice(0, 19)}</td>
                  <td className="px-4 py-3 text-slate-500">{f.fileSize} B</td>
                  <td className="px-4 py-3 text-slate-500">{f.collectionName || "—"}</td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      className="text-rose-600 hover:underline"
                      onClick={() => setPendingDeleteId(f.id)}
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {pendingDeleteId != null ? (
        <ConfirmModal
          title="删除文件"
          message="确定删除该文件？"
          confirmText="删除"
          danger
          onCancel={() => setPendingDeleteId(null)}
          onConfirm={() => {
            const id = pendingDeleteId;
            setPendingDeleteId(null);
            void deleteFile(id).then(reload);
          }}
        />
      ) : null}
    </div>
  );
}
