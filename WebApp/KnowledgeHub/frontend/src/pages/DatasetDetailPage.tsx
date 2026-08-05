import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Eye, FileUp, Pencil, Plus, Search, Trash2, Upload } from "lucide-react";
import {
  createDocument,
  deleteDocument,
  fetchMeta,
  getIngestProgress,
  ingestDocument,
  listCollections,
  listDocuments,
  updateCollection,
  updateDocument,
  type ChunkStrategy,
  type IngestProgress,
  type KhCollection,
  type KhDocument,
} from "@/lib/api";
import { ConfirmModal, ModalShell, NamePromptModal } from "@/components/Modals";

const TEXT_EXTS = /\.(md|markdown|txt|csv|json|yml|yaml|log)$/i;
const BINARY_EXTS = /\.(docx|pdf)$/i;
const ALLOWED_EXTS = /\.(md|markdown|txt|csv|json|yml|yaml|log|docx|pdf)$/i;

function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error(`读取失败：${file.name}`));
    reader.readAsText(file, "utf-8");
  });
}

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const raw = String(reader.result || "");
      const i = raw.indexOf(",");
      resolve(i >= 0 ? raw.slice(i + 1) : raw);
    };
    reader.onerror = () => reject(new Error(`读取失败：${file.name}`));
    reader.readAsDataURL(file);
  });
}

function titleFromFileName(name: string) {
  return name.replace(/\.[^.]+$/, "") || name;
}

function formatBytes(n?: number) {
  if (!n) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function statusLabel(status?: string) {
  if (status === "ready") return "已解析";
  if (status === "parsing") return "解析中";
  if (status === "failed") return "失败";
  if (status === "draft") return "草稿";
  return status || "—";
}

function embedLabel(s?: string) {
  if (s === "ready") return "已向量";
  if (s === "error") return "失败";
  return "未向量";
}

export function DatasetDetailPage() {
  const { id } = useParams();
  const collId = Number(id);
  const [coll, setColl] = useState<KhCollection | null>(null);
  const [docs, setDocs] = useState<KhDocument[]>([]);
  const [strategies, setStrategies] = useState<ChunkStrategy[]>([]);
  const [q, setQ] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const [parsingId, setParsingId] = useState<number | null>(null);
  const [parseProgress, setParseProgress] = useState<IngestProgress | null>(null);
  const [parseMeta, setParseMeta] = useState<{
    title: string;
    index?: number;
    total?: number;
  } | null>(null);
  const [show, setShow] = useState(false);
  const [mode, setMode] = useState<"upload" | "paste">("upload");
  const [parseOnCreate, setParseOnCreate] = useState(true);
  const [chunkStrategy, setChunkStrategy] = useState("markdown_heading");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<KhDocument | null>(null);
  const [renameColl, setRenameColl] = useState(false);
  const [renameDoc, setRenameDoc] = useState<KhDocument | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const strategyLabel = (sid?: string) =>
    strategies.find((s) => s.id === sid)?.labelZh || sid || "—";

  const reload = async () => {
    const cols = await listCollections();
    setColl(cols.find((c) => c.id === collId) || null);
    setDocs(await listDocuments(collId));
  };

  useEffect(() => {
    if (!collId) return;
    void reload().catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [collId]);

  useEffect(() => {
    void fetchMeta()
      .then((m) => {
        const list = m.chunkStrategies || [];
        setStrategies(list);
        if (list.length && !list.some((s) => s.id === chunkStrategy)) {
          setChunkStrategy(list[0].id);
        }
      })
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (parsingId == null) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const p = await getIngestProgress(parsingId);
        if (!cancelled) setParseProgress(p);
      } catch {
        /* ignore poll errors */
      }
    };
    void tick();
    const t = window.setInterval(() => void tick(), 400);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [parsingId]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return docs;
    return docs.filter(
      (d) =>
        d.title.toLowerCase().includes(needle) ||
        (d.fileName || "").toLowerCase().includes(needle),
    );
  }, [docs, q]);

  const resetForm = () => {
    setTitle("");
    setBody("");
    setPendingFiles([]);
    setMode("upload");
    setParseOnCreate(true);
    setChunkStrategy(
      strategies.find((s) => s.id === "markdown_heading")?.id ||
        strategies[0]?.id ||
        "markdown_heading",
    );
    setBusy(false);
    setDragOver(false);
  };

  const closeModal = () => {
    setShow(false);
    resetForm();
  };

  const pickFiles = (files: FileList | File[]) => {
    const list = Array.from(files);
    if (!list.length) return;
    setPendingFiles((prev) => {
      const names = new Set(prev.map((f) => f.name + f.size));
      const next = [...prev];
      for (const f of list) {
        const key = f.name + f.size;
        if (!names.has(key)) next.push(f);
      }
      return next;
    });
  };

  const runIngest = async (
    doc: { id: number; title: string },
    meta?: { index?: number; total?: number },
  ) => {
    setErr(null);
    setOkMsg(null);
    setParsingId(doc.id);
    setParseMeta({ title: doc.title, index: meta?.index, total: meta?.total });
    setParseProgress({
      documentId: doc.id,
      phase: "starting",
      done: 0,
      total: 0,
      percent: 1,
      title: doc.title,
      message: "开始解析…",
    });
    try {
      const res = await ingestDocument(doc.id);
      await reload();
      const emb = res.embeddedCount ?? 0;
      if (res.embedError) {
        setErr(
          `「${doc.title}」已分块 ${res.chunkCount}，但 Embedding 失败：${res.embedError}`,
        );
      } else if (emb > 0) {
        setOkMsg(`「${doc.title}」解析完成：${res.chunkCount} 块，已向量 ${emb}`);
      } else {
        setOkMsg(
          `「${doc.title}」解析完成：${res.chunkCount} 块（未写入向量，请检查默认 Embedding 配置）`,
        );
      }
      window.setTimeout(() => setOkMsg(null), 5000);
      return res;
    } finally {
      setParsingId(null);
      setParseMeta(null);
      setParseProgress(null);
    }
  };

  const saveUpload = async () => {
    if (!pendingFiles.length) {
      setErr("请先选择文件");
      return;
    }
    if (!chunkStrategy) {
      setErr("请选择分块方法");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const files = [...pendingFiles];
      const singleTitle = title.trim();
      closeModal();
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const isBinary = BINARY_EXTS.test(file.name);
        const isText =
          TEXT_EXTS.test(file.name) ||
          (!isBinary && (file.type.startsWith("text/") || ALLOWED_EXTS.test(file.name)));
        if (!isBinary && !isText) {
          throw new Error(
            `暂不支持「${file.name}」。请上传 .md / .txt / .docx / .pdf`,
          );
        }
        const docTitle =
          files.length === 1 && singleTitle
            ? singleTitle
            : titleFromFileName(file.name);
        let created: KhDocument;
        if (isBinary) {
          created = await createDocument({
            collectionId: collId,
            title: docTitle,
            sourceType: "file",
            fileName: file.name,
            fileSize: file.size,
            chunkStrategy,
            ingest: false,
            contentBase64: await readFileAsBase64(file),
          });
        } else {
          const text = await readFileAsText(file);
          if (!text.trim()) throw new Error(`「${file.name}」内容为空`);
          created = await createDocument({
            collectionId: collId,
            title: docTitle,
            body: text,
            sourceType: "file",
            fileName: file.name,
            fileSize: file.size,
            chunkStrategy,
            ingest: false,
          });
        }
        await reload();
        if (parseOnCreate) {
          await runIngest(
            { id: created.id, title: created.title || docTitle },
            { index: i + 1, total: files.length },
          );
        }
      }
      if (!parseOnCreate) await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      await reload().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };

  const onPasteAdd = async () => {
    if (!body.trim()) {
      setErr("请粘贴正文，或改用上传文件");
      return;
    }
    if (!chunkStrategy) {
      setErr("请选择分块方法");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const docTitle = title.trim() || "未命名文档";
      const textBody = body;
      const shouldParse = parseOnCreate;
      closeModal();
      const created = await createDocument({
        collectionId: collId,
        title: docTitle,
        body: textBody,
        sourceType: "text",
        chunkStrategy,
        ingest: false,
      });
      await reload();
      if (shouldParse) {
        await runIngest({ id: created.id, title: created.title || docTitle });
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      await reload().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };

  const onParse = async (doc: KhDocument) => {
    try {
      await runIngest({ id: doc.id, title: doc.title });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const onToggleEnabled = async (doc: KhDocument) => {
    const next = doc.enabled === false;
    try {
      setErr(null);
      const updated = await updateDocument(doc.id, { enabled: next });
      setDocs((prev) =>
        prev.map((d) => (d.id === doc.id ? { ...d, ...updated } : d)),
      );
      setOkMsg(
        next
          ? `已启用「${doc.title}」，可参与检索/问答`
          : `已停用「${doc.title}」，不再进入检索/问答`,
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const pct = Math.max(0, Math.min(100, parseProgress?.percent ?? 0));
  const progressLabel =
    parseProgress?.message ||
    (parsingId != null ? "正在解析，请稍候…" : "");

  return (
    <div>
      <div className="text-sm text-slate-500">
        <Link to="/datasets" className="hover:underline">
          知识库
        </Link>
        <span className="mx-1.5">›</span>
        <span className="text-slate-800">{coll?.name || `#${collId}`}</span>
      </div>

      <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold">{coll?.name || `知识库 #${collId}`}</h1>
            <button
              type="button"
              title="重命名知识库"
              className="rounded p-1.5 text-slate-400 hover:bg-sky-50 hover:text-sky-700"
              onClick={() => setRenameColl(true)}
            >
              <Pencil className="h-4 w-4" />
            </button>
          </div>
          <p className="mt-1 text-xs text-slate-400">{docs.length} 个文件</p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to={`/datasets/${collId}/search`}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 hover:border-sky-300"
          >
            <Search className="h-4 w-4" />
            检索测试
          </Link>
          <button
            type="button"
            className="inline-flex items-center gap-1 rounded-lg bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-50"
            disabled={parsingId != null}
            onClick={() => {
              resetForm();
              setShow(true);
            }}
          >
            <Plus className="h-4 w-4" />
            新增文件
          </button>
        </div>
      </div>

      {parsingId != null ? (
        <div className="sticky top-0 z-20 mt-4 rounded-xl border border-sky-200 bg-sky-50/95 px-4 py-3 shadow-sm backdrop-blur">
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-sky-900">
            <p className="font-medium">
              正在解析
              {parseMeta?.title ? `「${parseMeta.title}」` : ""}
              {parseMeta?.total && parseMeta.total > 1
                ? `（${parseMeta.index}/${parseMeta.total}）`
                : ""}
            </p>
            <p className="tabular-nums text-sky-700">{pct}%</p>
          </div>
          <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-sky-100">
            <div
              className="h-full rounded-full bg-sky-500 transition-[width] duration-300 ease-out"
              style={{ width: `${pct < 2 ? 2 : pct}%` }}
            />
          </div>
          <p className="mt-1.5 text-xs text-sky-700/90">{progressLabel}</p>
        </div>
      ) : null}

      <div className="mt-6 rounded-xl border border-slate-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
          <div>
            <h2 className="font-semibold text-slate-800">文件列表</h2>
            <p className="text-xs text-slate-400">
              解析成功后才能问答；停用后不进检索。失败可点「重试」
            </p>
          </div>
          <div className="flex items-center gap-1 rounded-lg border border-slate-200 px-2 py-1.5">
            <Search className="h-4 w-4 text-slate-400" />
            <input
              className="w-44 bg-transparent text-sm outline-none"
              placeholder="搜索文件名"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
        </div>

        {err && !show ? <p className="px-4 pt-3 text-sm text-rose-600">{err}</p> : null}
        {okMsg && !show ? (
          <p className="px-4 pt-3 text-sm text-emerald-700">{okMsg}</p>
        ) : null}

        <div className="overflow-x-auto">
          <table className="w-full min-w-[960px] text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">名称</th>
                <th className="px-4 py-2.5 font-medium">上传日期</th>
                <th className="px-4 py-2.5 font-medium">来源</th>
                <th className="px-4 py-2.5 font-medium">状态</th>
                <th className="px-4 py-2.5 font-medium">启用</th>
                <th className="px-4 py-2.5 font-medium">分块方法</th>
                <th className="px-4 py-2.5 font-medium">分块数</th>
                <th className="px-4 py-2.5 font-medium">Embedding</th>
                <th className="px-4 py-2.5 font-medium">动作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-slate-400">
                    暂无文档，点击「新增文件」上传或粘贴文本
                  </td>
                </tr>
              ) : (
                filtered.map((d) => (
                  <tr key={d.id} className="border-t border-slate-100 hover:bg-slate-50/80">
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-800">{d.title}</p>
                      <p className="text-xs text-slate-400">
                        {d.fileName || "粘贴文本"}
                        {d.fileSize ? ` · ${formatBytes(d.fileSize)}` : ""}
                      </p>
                      {d.parseError ? (
                        <p
                          className="mt-0.5 line-clamp-2 text-xs text-rose-500"
                          title={d.parseError}
                        >
                          {d.parseError}
                        </p>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 text-slate-500">
                      {d.createdAt?.slice(0, 19) || "—"}
                    </td>
                    <td className="px-4 py-3 text-slate-500">
                      {d.fileName || d.sourceType === "file" || d.sourceType === "pdf" || d.sourceType === "docx"
                        ? "本地上传"
                        : "粘贴"}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs ${
                          d.status === "ready"
                            ? "bg-emerald-50 text-emerald-700"
                            : d.status === "failed"
                              ? "bg-rose-50 text-rose-700"
                              : d.status === "parsing" || parsingId === d.id
                                ? "bg-sky-50 text-sky-700"
                                : "bg-slate-100 text-slate-600"
                        }`}
                        title={d.parseError || undefined}
                      >
                        {parsingId === d.id ? "解析中" : statusLabel(d.status)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        disabled={parsingId != null}
                        onClick={() => void onToggleEnabled(d)}
                        className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium transition disabled:opacity-50 ${
                          d.enabled === false
                            ? "bg-slate-100 text-slate-500 hover:bg-slate-200"
                            : "bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                        }`}
                        title={
                          d.enabled === false
                            ? "点击启用（可检索）"
                            : "点击停用（不进检索）"
                        }
                      >
                        {d.enabled === false ? "已停用" : "已启用"}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {strategyLabel(d.chunkStrategy)}
                    </td>
                    <td className="px-4 py-3 text-slate-600">{d.chunkCount ?? 0}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs ${
                          d.embedStatus === "ready"
                            ? "bg-cyan-50 text-cyan-700"
                            : d.embedStatus === "error"
                              ? "bg-rose-50 text-rose-700"
                              : "bg-slate-100 text-slate-500"
                        }`}
                      >
                        {embedLabel(d.embedStatus)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <Link
                          to={`/datasets/${collId}/documents/${d.id}`}
                          className="rounded p-1.5 text-slate-500 hover:bg-sky-50 hover:text-sky-700"
                          title="查看切片"
                        >
                          <Eye className="h-4 w-4" />
                        </Link>
                        <button
                          type="button"
                          className="rounded p-1.5 text-slate-400 hover:bg-sky-50 hover:text-sky-700"
                          title="重命名"
                          onClick={() => setRenameDoc(d)}
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        {d.status === "ready" ? (
                          <button
                            type="button"
                            className="rounded px-1.5 py-1 text-xs text-slate-500 hover:bg-slate-100 disabled:opacity-50"
                            title="重新解析（含 Embedding）"
                            disabled={parsingId != null}
                            onClick={() => void onParse(d)}
                          >
                            {parsingId === d.id ? "解析中…" : "重解析"}
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="rounded px-1.5 py-1 text-xs text-sky-700 hover:bg-sky-50 disabled:opacity-50"
                            title={
                              d.status === "failed" ? "解析失败，点击重试" : "解析"
                            }
                            disabled={parsingId != null}
                            onClick={() => void onParse(d)}
                          >
                            {parsingId === d.id
                              ? "解析中…"
                              : d.status === "failed"
                                ? "重试"
                                : "解析"}
                          </button>
                        )}
                        <button
                          type="button"
                          className="rounded p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                          title="删除"
                          onClick={() => setPendingDelete(d)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {show ? (
        <ModalShell title="上传文件" onClose={() => !busy && closeModal()}>
          <div className="mb-3 flex items-center justify-between gap-3">
            <span className="text-sm text-slate-700">创建时解析</span>
            <button
              type="button"
              role="switch"
              aria-checked={parseOnCreate}
              disabled={busy}
              onClick={() => setParseOnCreate((v) => !v)}
              className={`relative h-6 w-11 rounded-full transition ${
                parseOnCreate ? "bg-teal-500" : "bg-slate-300"
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition ${
                  parseOnCreate ? "translate-x-5" : ""
                }`}
              />
            </button>
          </div>

          <div className="mb-3 flex rounded-lg bg-slate-100 p-0.5 text-sm">
            <button
              type="button"
              className={`flex-1 rounded-md py-1.5 ${mode === "upload" ? "bg-white shadow-sm" : "text-slate-500"}`}
              onClick={() => setMode("upload")}
              disabled={busy}
            >
              上传文件
            </button>
            <button
              type="button"
              className={`flex-1 rounded-md py-1.5 ${mode === "paste" ? "bg-white shadow-sm" : "text-slate-500"}`}
              onClick={() => setMode("paste")}
              disabled={busy}
            >
              粘贴文本
            </button>
          </div>

          <label className="block text-xs text-slate-500">分块方法</label>
          <select
            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            value={chunkStrategy}
            onChange={(e) => setChunkStrategy(e.target.value)}
            disabled={busy}
          >
            {strategies.map((s) => (
              <option key={s.id} value={s.id}>
                {s.labelZh}
              </option>
            ))}
          </select>
          <p className="mt-1 text-[11px] text-slate-400">
            本次上传的文件共用该分块方法；不同文件可分批上传并选不同策略。
          </p>

          <label className="mt-3 block text-xs text-slate-500">标题（可选）</label>
          <input
            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            placeholder="多文件时忽略，默认用文件名"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={busy}
          />

          {mode === "upload" ? (
            <>
              <label className="mt-3 block text-xs text-slate-500">文件</label>
              <input
                ref={fileRef}
                type="file"
                accept=".md,.markdown,.txt,.csv,.json,.yml,.yaml,.log,.docx,.pdf,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                multiple
                className="hidden"
                onChange={(e) => {
                  if (e.target.files?.length) pickFiles(e.target.files);
                  e.target.value = "";
                }}
              />
              <button
                type="button"
                disabled={busy}
                onClick={() => fileRef.current?.click()}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  if (e.dataTransfer.files?.length) pickFiles(e.dataTransfer.files);
                }}
                className={`mt-1 flex w-full flex-col items-center gap-2 rounded-xl border border-dashed px-4 py-10 text-sm transition ${
                  dragOver
                    ? "border-sky-400 bg-sky-50 text-sky-700"
                    : "border-slate-300 bg-slate-50 text-slate-500 hover:border-sky-400 hover:text-sky-700"
                }`}
              >
                <Upload className="h-8 w-8" />
                <span className="font-medium">点击或拖拽文件至此区域即可上传</span>
                <span className="px-4 text-center text-xs text-slate-400">
                  支持 .md / .txt / .docx / .pdf（可批量）。扫描版 PDF 无文字层时无法抽取。
                </span>
              </button>
              {pendingFiles.length ? (
                <ul className="mt-3 max-h-28 space-y-1 overflow-auto text-xs text-slate-600">
                  {pendingFiles.map((f) => (
                    <li
                      key={`${f.name}-${f.size}`}
                      className="flex items-center justify-between gap-2 rounded bg-slate-50 px-2 py-1"
                    >
                      <span className="truncate">
                        {f.name} · {formatBytes(f.size)}
                      </span>
                      <button
                        type="button"
                        className="shrink-0 text-rose-600 hover:underline"
                        disabled={busy}
                        onClick={() =>
                          setPendingFiles((prev) =>
                            prev.filter((x) => !(x.name === f.name && x.size === f.size)),
                          )
                        }
                      >
                        移除
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
              <div className="mt-4 flex justify-end gap-2">
                <button
                  type="button"
                  className="rounded-lg border px-3 py-2 text-sm"
                  disabled={busy}
                  onClick={closeModal}
                >
                  取消
                </button>
                <button
                  type="button"
                  className="rounded-lg bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-60"
                  disabled={busy || !pendingFiles.length}
                  onClick={() => void saveUpload()}
                >
                  {busy ? "保存中…" : "保存"}
                </button>
              </div>
            </>
          ) : (
            <>
              <textarea
                className="mt-3 h-48 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                placeholder="粘贴 Markdown / 文本正文"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                disabled={busy}
              />
              <div className="mt-4 flex justify-end gap-2">
                <button
                  type="button"
                  className="rounded-lg border px-3 py-2 text-sm"
                  disabled={busy}
                  onClick={closeModal}
                >
                  取消
                </button>
                <button
                  type="button"
                  className="inline-flex items-center gap-1 rounded-lg bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-60"
                  disabled={busy}
                  onClick={() => void onPasteAdd()}
                >
                  <FileUp className="h-4 w-4" />
                  {busy ? "保存中…" : "保存"}
                </button>
              </div>
            </>
          )}

          {err && show ? <p className="mt-3 text-sm text-rose-600">{err}</p> : null}
        </ModalShell>
      ) : null}

      {pendingDelete ? (
        <ConfirmModal
          title="删除文档"
          message={`确定删除「${pendingDelete.title}」？切片会一并删除。`}
          confirmText="删除"
          danger
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => {
            const docId = pendingDelete.id;
            setPendingDelete(null);
            void deleteDocument(docId)
              .then(reload)
              .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
          }}
        />
      ) : null}

      {renameColl && coll ? (
        <NamePromptModal
          title="重命名知识库"
          label="名称"
          defaultValue={coll.name}
          onCancel={() => setRenameColl(false)}
          onConfirm={(v) => {
            setRenameColl(false);
            void updateCollection(collId, { name: v })
              .then(reload)
              .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
          }}
        />
      ) : null}

      {renameDoc ? (
        <NamePromptModal
          title="重命名文档"
          label="标题"
          defaultValue={renameDoc.title}
          onCancel={() => setRenameDoc(null)}
          onConfirm={(v) => {
            const docId = renameDoc.id;
            setRenameDoc(null);
            void updateDocument(docId, { title: v })
              .then(reload)
              .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
          }}
        />
      ) : null}
    </div>
  );
}
