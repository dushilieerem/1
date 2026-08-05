import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import {
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Search,
  Settings2,
  Trash2,
} from "lucide-react";
import { CitationMark } from "@/components/CitationMark";
import {
  appendConversationMessage,
  askKh,
  clearConversationMessages,
  createConversation,
  deleteConversation,
  listChats,
  listCollections,
  listConversationMessages,
  listConversations,
  searchChunks,
  updateChat,
  type KhChat,
  type KhChatMessage,
  type KhCollection,
  type KhConversation,
  type KhSearchHit,
} from "@/lib/api";

type ChatTurn = {
  id: string;
  query: string;
  answer?: string;
  grounded?: boolean;
  mode?: string;
  totalCandidates?: number;
  hits: KhSearchHit[];
  model?: string | null;
  error?: string;
  /** 已上屏、等待 ask 返回 */
  pending?: boolean;
};

function snippet(text: string, max = 180) {
  const t = (text || "")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/#{1,6}\s*/g, "")
    .replace(/\*\*/g, "")
    .replace(/`+/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max)}…`;
}

/** 轻度清理，保留 [1][2] 供引用角标 */
function cleanAnswer(text: string) {
  return (text || "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function AnswerWithCitations({
  answer,
  hits,
}: {
  answer: string;
  hits: KhSearchHit[];
}) {
  // 同一检索块编号只保留首次角标，避免 [1][1][1] 刷屏
  const seen = new Set<number>();
  const md = cleanAnswer(answer).replace(/\[(\d+)\]/g, (_m, n: string) => {
    const idx = Number(n);
    if (seen.has(idx)) return "";
    seen.add(idx);
    return `[↗](#cite-${n})`;
  });
  return (
    <div className="kh-md text-sm leading-relaxed text-slate-800">
      <ReactMarkdown
        components={{
          a: ({ href, children }) => {
            const m = /^#cite-(\d+)$/.exec(href || "");
            if (m) {
              const idx = Number(m[1]);
              return <CitationMark index={idx} hit={hits[idx - 1]} />;
            }
            return (
              <a href={href} className="text-[var(--kh-teal-deep)] underline">
                {children}
              </a>
            );
          },
        }}
      >
        {md}
      </ReactMarkdown>
    </div>
  );
}

function messagesToTurns(messages: KhChatMessage[]): ChatTurn[] {
  const turns: ChatTurn[] = [];
  let pending: ChatTurn | null = null;
  for (const m of messages) {
    if (m.role === "user") {
      if (pending) turns.push(pending);
      pending = {
        id: String(m.id),
        query: m.content,
        hits: [],
      };
      continue;
    }
    if (m.role === "assistant" && pending) {
      const meta = m.meta || {};
      const hits = Array.isArray(meta.hits) ? (meta.hits as KhSearchHit[]) : [];
      pending.mode = typeof meta.mode === "string" ? meta.mode : undefined;
      pending.totalCandidates =
        typeof meta.totalCandidates === "number" ? meta.totalCandidates : undefined;
      pending.hits = hits;
      pending.error = typeof meta.error === "string" ? meta.error : undefined;
      if (typeof meta.answer === "string") pending.answer = meta.answer;
      else if (meta.kind === "answer" && m.content) pending.answer = m.content;
      else if (m.content && meta.kind !== "retrieval") pending.answer = m.content;
      if (typeof meta.grounded === "boolean") pending.grounded = meta.grounded;
      if (typeof meta.model === "string") pending.model = meta.model;
      turns.push(pending);
      pending = null;
    }
  }
  if (pending) turns.push(pending);
  return turns;
}

export function ChatDetailPage() {
  const { id } = useParams();
  const chatId = Number(id);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const convParam = searchParams.get("c");
  const activeConvId = convParam ? Number(convParam) : null;

  const [chat, setChat] = useState<KhChat | null>(null);
  const [collections, setCollections] = useState<KhCollection[]>([]);
  const [conversations, setConversations] = useState<KhConversation[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [convFilter, setConvFilter] = useState("");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [topK, setTopK] = useState(5);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const filteredConvs = useMemo(() => {
    const q = convFilter.trim().toLowerCase();
    if (!q) return conversations;
    return conversations.filter((c) => c.title.toLowerCase().includes(q));
  }, [conversations, convFilter]);

  const activeConv =
    conversations.find((c) => c.id === activeConvId) || conversations[0] || null;

  const selectConv = (cid: number) => {
    setSearchParams({ c: String(cid) }, { replace: true });
  };

  const reloadConversations = async () => {
    const list = await listConversations(chatId);
    setConversations(list);
    return list;
  };

  useEffect(() => {
    setHistoryLoaded(false);
    setTurns([]);
    void Promise.all([listChats(), listCollections(), listConversations(chatId)])
      .then(([chats, cols, convs]) => {
        const c = chats.find((x) => x.id === chatId) || null;
        setChat(c);
        setCollections(cols);
        setConversations(convs);
        if (!convs.length) {
          setHistoryLoaded(true);
          return;
        }
        const wanted =
          (activeConvId && convs.find((x) => x.id === activeConvId)) || convs[0];
        if (!activeConvId || wanted.id !== activeConvId) {
          setSearchParams({ c: String(wanted.id) }, { replace: true });
        }
      })
      .catch((e) => {
        setErr(e instanceof Error ? e.message : String(e));
        setHistoryLoaded(true);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only reload when chat changes
  }, [chatId]);

  useEffect(() => {
    if (!activeConvId || Number.isNaN(activeConvId)) return;
    setHistoryLoaded(false);
    setTurns([]);
    void listConversationMessages(activeConvId)
      .then((messages) => {
        setTurns(messagesToTurns(messages));
        setHistoryLoaded(true);
      })
      .catch((e) => {
        setErr(e instanceof Error ? e.message : String(e));
        setHistoryLoaded(true);
      });
  }, [activeConvId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [turns, busy]);

  const save = async (patch: Partial<KhChat>) => {
    if (!chat) return;
    try {
      const next = await updateChat(chat.id, patch);
      setChat(next);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const persistTurn = async (
    conversationId: number,
    turn: {
      query: string;
      answer?: string;
      grounded?: boolean;
      mode?: string;
      totalCandidates?: number;
      hits: KhSearchHit[];
      model?: string | null;
      error?: string;
    },
  ) => {
    await appendConversationMessage(conversationId, {
      role: "user",
      content: turn.query,
    });
    const kind = turn.answer != null && !turn.error ? "answer" : "retrieval";
    await appendConversationMessage(conversationId, {
      role: "assistant",
      content: turn.error
        ? turn.error
        : turn.answer ||
          (turn.hits.length
            ? `检索预览 Top${turn.hits.length}`
            : "未命中切片"),
      meta: {
        kind,
        mode: turn.mode,
        totalCandidates: turn.totalCandidates,
        hits: turn.hits,
        answer: turn.answer,
        grounded: turn.grounded,
        model: turn.model,
        ...(turn.error ? { error: turn.error } : {}),
      },
    });
  };

  const onNewConversation = async () => {
    if (!chat || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const conv = await createConversation(chat.id, "新会话");
      const list = await reloadConversations();
      setConversations(list);
      selectConv(conv.id);
      setTurns([]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onDeleteConversation = async (cid: number) => {
    if (!chat || busy) return;
    if (!window.confirm("删除该会话及其全部消息？")) return;
    setBusy(true);
    setErr(null);
    try {
      await deleteConversation(cid);
      const list = await reloadConversations();
      const next = list[0];
      if (next) selectConv(next.id);
      else setTurns([]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const runRetrieve = async () => {
    if (!chat || busy || !activeConv) return;
    const q = draft.trim();
    if (!q) {
      setErr("请输入问题");
      return;
    }
    if (!chat.collectionIds.length) {
      setErr("请先在右侧「聊天设置」勾选至少一个关联知识库");
      setSettingsOpen(true);
      return;
    }
    setBusy(true);
    setErr(null);
    setDraft("");
    const turnId = `${Date.now()}`;
    // 先上屏用户问题 + AI「思考中」，再等接口
    setTurns((prev) => [
      ...prev,
      { id: turnId, query: q, hits: [], pending: true },
    ]);
    let turn: ChatTurn;
    try {
      try {
        const res = await askKh({
          query: q,
          collectionIds: chat.collectionIds,
          chatId: chat.id,
          topK,
        });
        turn = {
          id: turnId,
          query: q,
          answer: res.answer,
          grounded: res.grounded,
          mode: res.mode,
          totalCandidates: res.totalCandidates,
          hits: res.hits || [],
          model: res.model,
        };
      } catch (askErr) {
        const msg = askErr instanceof Error ? askErr.message : String(askErr);
        if (/未配置默认 LLM|LLM/i.test(msg)) {
          const res = await searchChunks({
            query: q,
            collectionIds: chat.collectionIds,
            topK,
          });
          turn = {
            id: turnId,
            query: q,
            mode: res.mode,
            totalCandidates: res.totalCandidates,
            hits: res.hits || [],
          };
          setErr("默认 LLM 未配置，已回落为检索预览（设置页可配）");
        } else {
          throw askErr;
        }
      }
    } catch (e) {
      turn = {
        id: turnId,
        query: q,
        hits: [],
        error: e instanceof Error ? e.message : String(e),
      };
    }
    setTurns((prev) => prev.map((t) => (t.id === turnId ? turn : t)));
    try {
      await persistTurn(activeConv.id, turn);
      await reloadConversations();
    } catch (e) {
      setErr(
        `结果已展示，但历史未写入：${e instanceof Error ? e.message : String(e)}`,
      );
    } finally {
      setBusy(false);
    }
  };

  const clearHistory = async () => {
    if (!activeConv || busy) return;
    if (!window.confirm("清空当前会话全部历史记录？")) return;
    setBusy(true);
    setErr(null);
    try {
      await clearConversationMessages(activeConv.id);
      setTurns([]);
      await reloadConversations();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!chat) {
    return (
      <div className="flex h-[calc(100vh-3.5rem)] items-center justify-center text-slate-500">
        {err || "加载中…"}
      </div>
    );
  }

  const linkedNames = collections
    .filter((c) => chat.collectionIds.includes(c.id))
    .map((c) => c.name);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] min-h-0 w-full overflow-hidden border-t border-[var(--kh-line)] bg-white/85 backdrop-blur-sm">
      {sidebarOpen ? (
        <aside className="flex w-64 shrink-0 flex-col border-r border-[var(--kh-line)] bg-gradient-to-b from-[#f3faf8] to-[#eef6f4]">
          <div className="flex items-center gap-2 border-b border-[var(--kh-line)] px-3 py-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--kh-cyan)] to-[var(--kh-teal-deep)] text-xs font-bold text-white shadow-sm">
              {chat.name.slice(0, 1).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-[var(--kh-ink)]">{chat.name}</p>
              <p className="truncate text-[11px] text-slate-500">
                {linkedNames.length ? linkedNames.join("、") : "未关联知识库"}
              </p>
            </div>
            <button
              type="button"
              className="rounded-lg p-1 text-slate-400 hover:bg-white/80"
              title="收起会话栏"
              onClick={() => setSidebarOpen(false)}
            >
              <PanelLeftClose className="h-4 w-4" />
            </button>
          </div>

          <div className="flex items-center justify-between px-3 pt-3">
            <p className="text-xs text-slate-500">
              会话 <span className="font-semibold text-[var(--kh-ink)]">{conversations.length}</span>
            </p>
            <button
              type="button"
              disabled={busy}
              className="rounded-lg border border-teal-200/80 bg-white p-1 text-[var(--kh-teal-deep)] hover:bg-teal-50 disabled:opacity-40"
              title="新建会话"
              onClick={() => void onNewConversation()}
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>

          <div className="px-3 pt-2">
            <div className="flex items-center gap-1.5 rounded-xl border border-[var(--kh-line)] bg-white/80 px-2 py-1.5">
              <Search className="h-3.5 w-3.5 text-slate-400" />
              <input
                className="w-full bg-transparent text-xs outline-none"
                placeholder="搜索会话"
                value={convFilter}
                onChange={(e) => setConvFilter(e.target.value)}
              />
            </div>
          </div>

          <div className="mt-2 min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
            {filteredConvs.length === 0 ? (
              <p className="px-2 py-6 text-center text-xs text-slate-400">暂无会话</p>
            ) : (
              filteredConvs.map((c) => {
                const active = activeConv?.id === c.id;
                return (
                  <div
                    key={c.id}
                    className={`group flex items-center gap-1 rounded-xl px-2 py-2 text-sm transition ${
                      active
                        ? "bg-white text-[var(--kh-teal-deep)] shadow-sm ring-1 ring-teal-200/70"
                        : "text-slate-600 hover:bg-white/70"
                    }`}
                  >
                    <button
                      type="button"
                      className="min-w-0 flex-1 truncate text-left"
                      onClick={() => selectConv(c.id)}
                    >
                      {c.title || "新会话"}
                    </button>
                    <button
                      type="button"
                      className="rounded p-0.5 text-slate-300 opacity-0 hover:bg-rose-50 hover:text-rose-600 group-hover:opacity-100"
                      title="删除会话"
                      onClick={() => void onDeleteConversation(c.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                );
              })
            )}
          </div>

          <div className="space-y-1 border-t border-[var(--kh-line)] p-2">
            <button
              type="button"
              className="flex w-full items-center gap-2 rounded-xl px-2 py-2 text-sm text-slate-600 hover:bg-white/80"
              onClick={() => setSettingsOpen(true)}
            >
              <Settings2 className="h-4 w-4" />
              聊天设置
            </button>
            <button
              type="button"
              disabled={busy || !turns.length}
              className="w-full rounded-xl px-2 py-2 text-left text-sm text-slate-500 hover:bg-white/80 disabled:opacity-40"
              onClick={() => void clearHistory()}
            >
              清空当前会话
            </button>
            <Link
              to="/chats"
              className="block rounded-xl px-2 py-2 text-sm text-slate-400 hover:bg-white/80 hover:text-slate-600"
            >
              返回应用列表
            </Link>
          </div>
        </aside>
      ) : (
        <aside className="flex w-12 shrink-0 flex-col items-center border-r border-[var(--kh-line)] bg-[#f3faf8] py-3">
          <button
            type="button"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-white"
            title="展开会话栏"
            onClick={() => setSidebarOpen(true)}
          >
            <PanelLeftOpen className="h-4 w-4" />
          </button>
          <button
            type="button"
            className="mt-3 rounded-lg p-1.5 text-[var(--kh-teal-deep)] hover:bg-white"
            title="新建会话"
            onClick={() => void onNewConversation()}
          >
            <Plus className="h-4 w-4" />
          </button>
          <button
            type="button"
            className="mt-2 rounded-lg p-1.5 text-slate-500 hover:bg-white"
            title="聊天设置"
            onClick={() => setSettingsOpen(true)}
          >
            <Settings2 className="h-4 w-4" />
          </button>
        </aside>
      )}

      <section className="flex min-w-0 flex-1 flex-col bg-[linear-gradient(180deg,#ffffff_0%,#f7fbfa_100%)]">
        <div className="flex items-center justify-between border-b border-[var(--kh-line)] px-5 py-3">
          <div>
            <p className="kh-display text-sm font-semibold text-[var(--kh-ink)]">
              {activeConv?.title || "新会话"}
            </p>
            <p className="text-[11px] text-slate-400">
              知识库问答（检索 + LLM）
              {historyLoaded
                ? turns.length
                  ? ` · ${turns.length} 轮`
                  : " · 暂无消息"
                : " · 加载中…"}
            </p>
          </div>
          <button
            type="button"
            className="rounded-xl border border-[var(--kh-line)] bg-white px-3 py-1.5 text-xs text-slate-600 hover:bg-[var(--kh-mist)]"
            onClick={() => setSettingsOpen((v) => !v)}
          >
            {settingsOpen ? "收起设置" : "聊天设置"}
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 py-4 sm:px-6">
          {turns.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
              <div className="kh-empty-orb flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-[var(--kh-cyan)] to-[var(--kh-teal-deep)] text-lg font-bold text-white shadow-lg shadow-teal-700/20">
                AI
              </div>
              <div className="max-w-md rounded-2xl border border-[var(--kh-line)] bg-white/90 px-5 py-4 text-sm text-slate-600 shadow-sm">
                {chat.opener || "你好！我是你的助理，有什么可以帮到你的吗？"}
              </div>
            </div>
          ) : (
            <div className="mx-auto w-full max-w-5xl flex-1 space-y-4">
              <div className="flex gap-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[var(--kh-cyan)] to-[var(--kh-teal-deep)] text-[10px] font-bold text-white">
                  AI
                </div>
                <div className="rounded-2xl rounded-tl-md border border-[var(--kh-line)] bg-white px-4 py-3 text-sm text-slate-600 shadow-sm">
                  {chat.opener || "你好！我是你的助理，有什么可以帮到你的吗？"}
                </div>
              </div>

              {turns.map((t) => (
                <div key={t.id} className="space-y-3">
                  <div className="flex justify-end gap-3">
                    <div className="max-w-[85%] rounded-2xl rounded-br-md bg-gradient-to-br from-[var(--kh-teal)] to-[var(--kh-teal-deep)] px-3.5 py-2 text-sm text-white shadow-sm">
                      {t.query}
                    </div>
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--kh-amber-soft)] text-xs font-semibold text-[#a86a08]">
                      我
                    </div>
                  </div>
                  <div className="flex gap-3">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[var(--kh-cyan)] to-[var(--kh-teal-deep)] text-[10px] font-bold text-white">
                      AI
                    </div>
                    <div className="min-w-0 flex-1 rounded-2xl rounded-tl-md border border-[var(--kh-line)] bg-white px-4 py-3.5 shadow-sm">
                      {t.pending ? (
                        <p className="text-sm font-medium text-[var(--kh-teal-deep)]">
                          思考中…
                        </p>
                      ) : t.error ? (
                        <p className="text-sm text-rose-600">{t.error}</p>
                      ) : (
                        <>
                          {t.answer != null ? (
                            <AnswerWithCitations answer={t.answer} hits={t.hits} />
                          ) : null}
                          {t.hits.length > 0 ? (
                            <details className="mt-3 rounded-xl border border-teal-100/80 bg-[var(--kh-mist)]/40 open:pb-1">
                              <summary className="cursor-pointer list-none px-3 py-2 text-xs text-slate-600 marker:content-none [&::-webkit-details-marker]:hidden">
                                <span className="inline-flex flex-wrap items-center gap-2">
                                  <Search className="h-3.5 w-3.5 text-[var(--kh-teal)]" />
                                  <span className="font-medium text-slate-700">
                                    {t.answer != null ? "参考来源" : "检索结果"}
                                  </span>
                                  {t.mode ? (
                                    <span className="rounded-md bg-white/80 px-1.5 py-0.5 font-mono text-[var(--kh-teal-deep)]">
                                      {t.mode}
                                    </span>
                                  ) : null}
                                  <span className="text-slate-400">
                                    {t.hits.length} 条
                                    {typeof t.totalCandidates === "number"
                                      ? ` / 候选 ${t.totalCandidates}`
                                      : ""}
                                  </span>
                                  {t.model ? (
                                    <span className="rounded bg-white/80 px-1.5 py-0.5 font-mono text-slate-500">
                                      {t.model}
                                    </span>
                                  ) : null}
                                </span>
                              </summary>
                              <ul className="space-y-2 px-3 pb-3">
                                {t.hits.map((h, i) => (
                                  <li
                                    key={`${t.id}-${h.chunkId}-${i}`}
                                    className="rounded-lg border border-white/80 bg-white/90 px-3 py-2"
                                  >
                                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                                      <span className="font-mono text-slate-500">#{i + 1}</span>
                                      <Link
                                        to={`/datasets/${h.collectionId}/documents/${h.documentId}`}
                                        className="font-medium text-[var(--kh-teal-deep)] hover:underline"
                                      >
                                        {h.documentTitle}
                                      </Link>
                                      {typeof h.meta?.title === "string" ? (
                                        <span className="truncate text-slate-500">
                                          {h.meta.title}
                                        </span>
                                      ) : null}
                                    </div>
                                    <p className="mt-1 text-sm leading-relaxed text-slate-600">
                                      {snippet(h.text, 160)}
                                    </p>
                                  </li>
                                ))}
                              </ul>
                            </details>
                          ) : t.answer == null ? (
                            <p className="text-sm text-slate-400">
                              未命中切片，可换个问法或检查知识库是否已向量化
                            </p>
                          ) : null}
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ))}

              <div ref={bottomRef} />
            </div>
          )}
          {turns.length === 0 ? <div ref={bottomRef} /> : null}
        </div>

        <div className="border-t border-[var(--kh-line)] bg-white/90 px-4 py-3 backdrop-blur">
          {err ? <p className="mb-2 text-xs text-rose-600">{err}</p> : null}
          <div className="mx-auto flex max-w-5xl items-center gap-2 rounded-2xl border border-[var(--kh-line)] bg-white px-3 py-2 shadow-sm">
            <input
              className="flex-1 bg-transparent text-sm outline-none disabled:opacity-60"
              placeholder={
                !activeConv
                  ? "请先新建会话…"
                  : chat.collectionIds.length
                    ? "输入问题，回车提问…"
                    : "请先在右侧勾选关联知识库…"
              }
              value={draft}
              disabled={busy || !activeConv}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void runRetrieve();
                }
              }}
            />
            <label className="hidden items-center gap-1 text-[11px] text-slate-400 sm:flex">
              TopK
              <input
                type="number"
                min={1}
                max={20}
                className="w-10 rounded border border-slate-200 px-1 py-0.5 text-xs"
                value={topK}
                disabled={busy}
                onChange={(e) =>
                  setTopK(Math.max(1, Math.min(20, Number(e.target.value) || 5)))
                }
              />
            </label>
            <button
              type="button"
              disabled={busy || !draft.trim() || !activeConv}
              className="kh-btn-primary rounded-xl px-3.5 py-1.5 text-sm disabled:opacity-50"
              onClick={() => void runRetrieve()}
            >
              {busy ? "思考中…" : "发送"}
            </button>
          </div>
        </div>
      </section>

      {settingsOpen ? (
        <aside className="w-80 shrink-0 overflow-y-auto border-l border-[var(--kh-line)] bg-white p-4">
          <div className="flex items-center justify-between">
            <h2 className="kh-display font-semibold text-[var(--kh-ink)]">聊天设置</h2>
            <button
              type="button"
              className="text-slate-400"
              onClick={() => setSettingsOpen(false)}
            >
              ×
            </button>
          </div>
          <label className="mt-4 block text-xs text-slate-500">助理姓名</label>
          <input
            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={chat.name}
            onChange={(e) => setChat({ ...chat, name: e.target.value })}
            onBlur={() => void save({ name: chat.name })}
          />
          <label className="mt-3 block text-xs text-slate-500">开场白</label>
          <textarea
            className="mt-1 h-20 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={chat.opener}
            onChange={(e) => setChat({ ...chat, opener: e.target.value })}
            onBlur={() => void save({ opener: chat.opener })}
          />
          <label className="mt-3 block text-xs text-slate-500">系统提示词</label>
          <textarea
            className="mt-1 h-28 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
            placeholder="可使用 {knowledge} 注入检索片段"
            value={chat.systemPrompt}
            onChange={(e) => setChat({ ...chat, systemPrompt: e.target.value })}
            onBlur={() => void save({ systemPrompt: chat.systemPrompt })}
          />
          <label className="mt-3 block text-xs text-slate-500">关联知识库（可多选）</label>
          <div className="mt-1 max-h-40 space-y-1 overflow-y-auto rounded-xl border border-slate-200 p-2">
            {collections.length === 0 ? (
              <p className="px-1 py-2 text-xs text-slate-400">暂无知识库</p>
            ) : (
              collections.map((c) => {
                const checked = chat.collectionIds.includes(c.id);
                return (
                  <label key={c.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => {
                        const next = checked
                          ? chat.collectionIds.filter((x) => x !== c.id)
                          : [...chat.collectionIds, c.id];
                        setChat({ ...chat, collectionIds: next });
                        void save({ collectionIds: next });
                      }}
                    />
                    {c.name}
                  </label>
                );
              })
            )}
          </div>
          {err ? <p className="mt-2 text-xs text-rose-600">{err}</p> : null}
          <button
            type="button"
            className="kh-btn-primary mt-4 w-full rounded-xl py-2 text-sm"
            onClick={() =>
              void save({
                name: chat.name,
                opener: chat.opener,
                systemPrompt: chat.systemPrompt,
                collectionIds: chat.collectionIds,
              })
            }
          >
            保存
          </button>
          <button
            type="button"
            className="mt-2 w-full text-xs text-slate-400 hover:underline"
            onClick={() => navigate("/chats")}
          >
            返回聊天应用列表
          </button>
        </aside>
      ) : null}
    </div>
  );
}
