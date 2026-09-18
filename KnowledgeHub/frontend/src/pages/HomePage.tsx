import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Database, MessageSquare, Plus, Sparkles, Trash2 } from "lucide-react";
import {
  createChat,
  createCollection,
  deleteChat,
  deleteCollection,
  listChats,
  listCollections,
  type KhChat,
  type KhCollection,
} from "@/lib/api";
import { ConfirmModal, ModalShell, NamePromptModal } from "@/components/Modals";

function Card({
  title,
  meta,
  to,
  tone,
  onDelete,
}: {
  title: string;
  meta: string;
  to: string;
  tone: "kb" | "chat";
  onDelete?: () => void;
}) {
  const letter = title.slice(0, 1).toUpperCase();
  return (
    <div className="group relative w-48 shrink-0 kh-fade-in">
      <Link
        to={to}
        className={`kh-card flex h-full min-h-[148px] flex-col gap-3 p-4 ${
          tone === "kb" ? "kh-card-kb" : "kh-card-chat"
        }`}
      >
        <div
          className={`flex h-11 w-11 items-center justify-center rounded-xl text-sm font-bold text-white shadow-sm ${
            tone === "kb"
              ? "bg-gradient-to-br from-[var(--kh-cyan)] to-[var(--kh-teal-deep)]"
              : "bg-gradient-to-br from-[var(--kh-amber)] to-[#c47b0a]"
          }`}
        >
          {letter}
        </div>
        <div>
          <p className="truncate pr-5 text-sm font-semibold text-[var(--kh-ink)]">{title}</p>
          <p className="mt-1 text-xs text-slate-500">{meta}</p>
        </div>
      </Link>
      {onDelete ? (
        <button
          type="button"
          title="删除"
          className="absolute right-2 top-2 rounded-lg p-1 text-slate-400 opacity-0 hover:bg-rose-50 hover:text-rose-600 group-hover:opacity-100"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onDelete();
          }}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      ) : null}
    </div>
  );
}

type PendingDelete =
  | { kind: "collection"; id: number; name: string }
  | { kind: "chat"; id: number; name: string }
  | null;

export function HomePage() {
  const navigate = useNavigate();
  const [collections, setCollections] = useState<KhCollection[]>([]);
  const [chats, setChats] = useState<KhChat[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [kbOpen, setKbOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [kbName, setKbName] = useState("");
  const [pendingDelete, setPendingDelete] = useState<PendingDelete>(null);

  const reload = async () => {
    const [c, h] = await Promise.all([listCollections(), listChats()]);
    setCollections(c);
    setChats(h);
  };

  useEffect(() => {
    void reload().catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  const onCreateKb = async () => {
    if (!kbName.trim()) return;
    try {
      const c = await createCollection({
        name: kbName.trim(),
      });
      setKbOpen(false);
      setKbName("");
      await reload();
      navigate(`/datasets/${c.id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const onCreateChat = async (name: string) => {
    try {
      const c = await createChat(name);
      setChatOpen(false);
      await reload();
      navigate(`/chats/${c.id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    const target = pendingDelete;
    setPendingDelete(null);
    try {
      if (target.kind === "collection") await deleteCollection(target.id);
      else await deleteChat(target.id);
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="space-y-8 pb-10">
      <section className="kh-hero kh-fade-in px-6 py-8 sm:px-10 sm:py-10">
        <div className="relative z-10 max-w-2xl">
          <p className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs text-teal-50 ring-1 ring-white/15">
            <Sparkles className="h-3.5 w-3.5 text-[var(--kh-amber)]" />
            KnowledgeHub · 检索先行
          </p>
          <h1 className="kh-display mt-4 text-3xl font-bold tracking-tight sm:text-4xl">
            欢迎来到知识库平台
          </h1>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-teal-50/85 sm:text-base">
            把文档沉淀成可检索的知识，再用聊天应用完成问答。
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => setKbOpen(true)}
              className="rounded-xl bg-white px-4 py-2 text-sm font-semibold text-[var(--kh-ink)] shadow-sm hover:bg-teal-50"
            >
              新建知识库
            </button>
            <button
              type="button"
              onClick={() => setChatOpen(true)}
              className="rounded-xl border border-white/25 bg-white/10 px-4 py-2 text-sm font-medium text-white hover:bg-white/15"
            >
              新建聊天应用
            </button>
          </div>
        </div>
      </section>

      {err ? <p className="text-sm text-rose-600">{err}</p> : null}

      <section className="kh-panel rounded-2xl p-5 sm:p-6">
        <div className="mb-4 flex items-center gap-2 text-[var(--kh-ink)]">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--kh-mist)] text-[var(--kh-teal-deep)]">
            <Database className="h-4 w-4" />
          </div>
          <h2 className="kh-display font-semibold">知识库</h2>
          <Link to="/datasets" className="ml-auto text-sm text-[var(--kh-teal-deep)] hover:underline">
            查看全部 &gt;
          </Link>
        </div>
        <div className="flex gap-3 overflow-x-auto pb-1">
          {collections.slice(0, 8).map((c) => (
            <Card
              key={c.id}
              title={c.name}
              meta={`${c.documentCount} 个文件`}
              to={`/datasets/${c.id}`}
              tone="kb"
              onDelete={() =>
                setPendingDelete({ kind: "collection", id: c.id, name: c.name })
              }
            />
          ))}
          <button
            type="button"
            onClick={() => setKbOpen(true)}
            className="flex min-h-[148px] w-48 shrink-0 flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-teal-300/70 bg-teal-50/40 text-[var(--kh-teal-deep)] hover:border-[var(--kh-teal)] hover:bg-teal-50/70"
          >
            <Plus className="h-6 w-6" />
            <span className="text-sm font-medium">创建知识库</span>
          </button>
        </div>
      </section>

      <section className="kh-panel rounded-2xl p-5 sm:p-6">
        <div className="mb-4 flex items-center gap-2 text-[var(--kh-ink)]">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--kh-amber-soft)] text-[#a86a08]">
            <MessageSquare className="h-4 w-4" />
          </div>
          <h2 className="kh-display font-semibold">聊天应用</h2>
          <Link to="/chats" className="ml-auto text-sm text-[#a86a08] hover:underline">
            查看全部 &gt;
          </Link>
        </div>
        <div className="flex gap-3 overflow-x-auto pb-1">
          {chats.slice(0, 8).map((c) => (
            <Card
              key={c.id}
              title={c.name}
              meta={c.updatedAt?.slice(0, 16) || ""}
              to={`/chats/${c.id}`}
              tone="chat"
              onDelete={() => setPendingDelete({ kind: "chat", id: c.id, name: c.name })}
            />
          ))}
          <button
            type="button"
            onClick={() => setChatOpen(true)}
            className="flex min-h-[148px] w-48 shrink-0 flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-amber-300/80 bg-amber-50/50 text-[#a86a08] hover:border-[var(--kh-amber)] hover:bg-amber-50"
          >
            <Plus className="h-6 w-6" />
            <span className="text-sm font-medium">创建聊天应用</span>
          </button>
        </div>
      </section>

      {kbOpen ? (
        <ModalShell title="创建知识库" onClose={() => setKbOpen(false)}>
          <label className="block text-xs text-slate-500">名称</label>
          <input
            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            value={kbName}
            onChange={(e) => setKbName(e.target.value)}
            placeholder="请输入名称"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") void onCreateKb();
            }}
          />
          <p className="mt-2 text-xs text-slate-400">分块方法在上传文档时选择。</p>
          <div className="mt-5 flex justify-end gap-2">
            <button
              type="button"
              className="rounded-lg border px-3 py-2 text-sm"
              onClick={() => setKbOpen(false)}
            >
              取消
            </button>
            <button
              type="button"
              className="kh-btn-primary rounded-lg px-3 py-2 text-sm"
              onClick={() => void onCreateKb()}
            >
              创建
            </button>
          </div>
        </ModalShell>
      ) : null}

      {chatOpen ? (
        <NamePromptModal
          title="创建聊天应用"
          label="应用名称"
          defaultValue="未命名应用"
          onCancel={() => setChatOpen(false)}
          onConfirm={(v) => void onCreateChat(v)}
        />
      ) : null}

      {pendingDelete ? (
        <ConfirmModal
          title={pendingDelete.kind === "collection" ? "删除知识库" : "删除聊天应用"}
          message={
            pendingDelete.kind === "collection"
              ? `确定删除知识库「${pendingDelete.name}」？文档与切片会一并删除。`
              : `确定删除聊天「${pendingDelete.name}」？`
          }
          confirmText="删除"
          danger
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => void confirmDelete()}
        />
      ) : null}
    </div>
  );
}
