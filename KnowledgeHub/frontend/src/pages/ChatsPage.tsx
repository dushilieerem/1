import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { MessageSquare, Plus, Trash2 } from "lucide-react";
import { createChat, deleteChat, listChats, type KhChat } from "@/lib/api";
import { ConfirmModal, NamePromptModal } from "@/components/Modals";

export function ChatsPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<KhChat[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<KhChat | null>(null);

  const reload = () =>
    listChats()
      .then(setItems)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));

  useEffect(() => {
    void reload();
  }, []);

  const onCreate = async (name: string) => {
    try {
      const c = await createChat(name.trim());
      setOpen(false);
      navigate(`/chats/${c.id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="pb-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="kh-display text-2xl font-bold text-[var(--kh-ink)]">聊天应用</h1>
          <p className="mt-1 text-sm text-slate-500">
            绑定知识库与提示词；进入后左侧「+」新建多轮会话。
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="kh-btn-primary inline-flex items-center gap-1 rounded-xl px-3.5 py-2 text-sm font-medium"
        >
          <Plus className="h-4 w-4" />
          创建聊天应用
        </button>
      </div>
      {err ? <p className="mt-3 text-sm text-rose-600">{err}</p> : null}
      {items.length === 0 ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="kh-card kh-card-chat mt-10 flex w-full max-w-lg flex-col items-center gap-3 py-20 text-slate-500 hover:border-[var(--kh-amber)]"
        >
          <MessageSquare className="h-8 w-8 text-[var(--kh-amber)]" />
          <span>尚未创建聊天应用</span>
          <Plus className="h-6 w-6" />
        </button>
      ) : (
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((c, i) => (
            <div
              key={c.id}
              className="kh-card kh-card-chat group relative min-h-[132px] p-5 kh-fade-in"
              style={{ animationDelay: `${i * 40}ms` }}
            >
              <Link to={`/chats/${c.id}`} className="block pr-8">
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--kh-amber)] to-[#c47b0a] text-sm font-bold text-white">
                  {c.name.slice(0, 1).toUpperCase()}
                </div>
                <p className="font-semibold text-[var(--kh-ink)]">{c.name}</p>
                <p className="mt-1 text-xs text-slate-500">{c.updatedAt?.slice(0, 19)}</p>
              </Link>
              <button
                type="button"
                title="删除"
                className="absolute right-3 top-3 rounded-lg p-1 text-slate-400 opacity-0 hover:bg-rose-50 hover:text-rose-600 group-hover:opacity-100"
                onClick={() => setPendingDelete(c)}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {open ? (
        <NamePromptModal
          title="创建聊天应用"
          label="应用名称"
          defaultValue="未命名应用"
          onCancel={() => setOpen(false)}
          onConfirm={(v) => void onCreate(v)}
        />
      ) : null}

      {pendingDelete ? (
        <ConfirmModal
          title="删除聊天应用"
          message={`确定删除应用「${pendingDelete.name}」及其全部会话？`}
          confirmText="删除"
          danger
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => {
            const id = pendingDelete.id;
            setPendingDelete(null);
            void deleteChat(id).then(reload);
          }}
        />
      ) : null}
    </div>
  );
}
