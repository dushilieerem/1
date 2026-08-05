import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Copy,
  LineChart,
  Loader2,
  MoreHorizontal,
  Pin,
  Plus,
  Trash2,
  Wand2,
  X,
} from "lucide-react";
import { FactorCodeEditor } from "@/components/FactorCodeEditor";
import {
  ygGenerateStrategyDraft,
  type AiStrategyDraft,
} from "@/lib/aiStrategyApi";
import {
  createStrategyProjectFromCode,
  openStrategyInNewTab,
} from "@/lib/strategyStore";
import { subscribeAuth } from "@/lib/auth";
import { aiHistoryStorageKey } from "@/lib/aiHistoryStorage";
import { newUuidV4 } from "@/lib/uuid";

const PROMPT_MAX = 2000;
const DESC_MAX = 40;
const HISTORY_MAX = 40;

type HistoryItem = {
  id: string;
  prompt: string;
  at: number;
  strategy_name: string;
  strategy_code: string;
  description: string;
  pinned?: boolean;
};

type WorkspaceSnap = {
  prompt: string;
  code: string;
  draft: AiStrategyDraft | null;
  validated: boolean;
};

function newIdempotencyKey() {
  return newUuidV4();
}

function loadHistory(): HistoryItem[] {
  try {
    const key = aiHistoryStorageKey("strategy");
    if (!key) return [];
    const raw = localStorage.getItem(key);
    if (!raw) return [];
    const list = JSON.parse(raw) as HistoryItem[];
    return Array.isArray(list) ? list.slice(0, HISTORY_MAX) : [];
  } catch {
    return [];
  }
}

function persistHistory(list: HistoryItem[]) {
  try {
    const key = aiHistoryStorageKey("strategy");
    if (!key) return;
    localStorage.setItem(key, JSON.stringify(list.slice(0, HISTORY_MAX)));
  } catch {
    /* ignore */
  }
}

function fmtTime(ts: number) {
  const d = new Date(ts);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function sortHistory(list: HistoryItem[]) {
  return [...list].sort((a, b) => {
    const ap = a.pinned ? 1 : 0;
    const bp = b.pinned ? 1 : 0;
    if (ap !== bp) return bp - ap;
    return b.at - a.at;
  });
}

function historyGroupLabel(ts: number) {
  const now = Date.now();
  const day = 86400000;
  if (now - ts < 7 * day) return "7 天内";
  const d = new Date(ts);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function AiStrategyGeneratePage() {
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [draft, setDraft] = useState<AiStrategyDraft | null>(null);
  const [code, setCode] = useState("");
  const [validated, setValidated] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>(() =>
    sortHistory(loadHistory()),
  );
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null);
  const [currentSnap, setCurrentSnap] = useState<WorkspaceSnap | null>(null);
  const [menuId, setMenuId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [sendBusy, setSendBusy] = useState(false);
  const [sendOpen, setSendOpen] = useState(false);
  const [sendName, setSendName] = useState("");
  const [sendDesc, setSendDesc] = useState("");
  const [sendFormErr, setSendFormErr] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    return subscribeAuth(() => {
      setHistory(sortHistory(loadHistory()));
      setActiveHistoryId(null);
      setCurrentSnap(null);
      setPrompt("");
      setCode("");
      setDraft(null);
      setValidated(false);
      setErr(null);
      setMenuId(null);
      setSendOpen(false);
    });
  }, []);

  useEffect(() => {
    if (!menuId) return;
    const onDoc = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuId(null);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [menuId]);

  const updateHistory = (next: HistoryItem[]) => {
    const sorted = sortHistory(next).slice(0, HISTORY_MAX);
    setHistory(sorted);
    persistHistory(sorted);
  };

  const pushHistory = (item: HistoryItem) => {
    setHistory((prev) => {
      const old = prev.find((h) => h.id === item.id);
      const merged = {
        ...item,
        pinned: old?.pinned ?? item.pinned ?? false,
      };
      const next = sortHistory([
        merged,
        ...prev.filter((h) => h.id !== item.id),
      ]).slice(0, HISTORY_MAX);
      persistHistory(next);
      return next;
    });
  };

  const grouped = useMemo(() => {
    const map = new Map<string, HistoryItem[]>();
    for (const h of history) {
      const key = h.pinned ? "置顶" : historyGroupLabel(h.at);
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(h);
    }
    return [...map.entries()];
  }, [history]);

  const onGenerate = useCallback(async () => {
    const text = prompt.trim();
    if (!text) {
      setErr("请先写研究假设");
      return;
    }
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setBusy(true);
    setErr(null);
    try {
      const data = await ygGenerateStrategyDraft(
        {
          prompt: text,
          idempotency_key: newIdempotencyKey(),
          context: { universe: "CSI500", frequency: "1d" },
        },
        ac.signal,
      );
      if (data.status !== "ready" || !data.strategy) {
        const errs = data.validation?.errors || [];
        setDraft(null);
        setCode("");
        setValidated(false);
        setErr(
          errs.length
            ? `未通过校验：${errs.join("；")}`
            : "生成失败，请换个说法再试",
        );
        return;
      }
      const id = data.generation_id || newIdempotencyKey();
      setDraft(data.strategy);
      setCode(data.strategy.strategy_code);
      setValidated(true);
      setActiveHistoryId(id);
      setCurrentSnap(null);
      pushHistory({
        id,
        prompt: text,
        at: Date.now(),
        strategy_name: data.strategy.strategy_name,
        strategy_code: data.strategy.strategy_code,
        description: data.strategy.description || "",
      });
    } catch (e) {
      if ((e as Error)?.name === "AbortError") return;
      setDraft(null);
      setCode("");
      setValidated(false);
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [prompt]);

  const onPickHistory = (h: HistoryItem) => {
    setMenuId(null);
    if (h.id === activeHistoryId) return;
    if (activeHistoryId === null && (prompt.trim() || code.trim() || draft)) {
      setCurrentSnap({ prompt, code, draft, validated });
    }
    setActiveHistoryId(h.id);
    setPrompt(h.prompt);
    setCode(h.strategy_code);
    setValidated(true);
    setDraft({
      strategy_name: h.strategy_name,
      strategy_code: h.strategy_code,
      description: h.description,
      used_fields: [],
      assumptions: [],
      warnings: [],
    });
    setErr(null);
  };

  const onReturnCurrent = () => {
    if (!currentSnap) return;
    setMenuId(null);
    setActiveHistoryId(null);
    setPrompt(currentSnap.prompt);
    setCode(currentSnap.code);
    setDraft(currentSnap.draft);
    setValidated(currentSnap.validated);
    setErr(null);
  };

  const onNewChat = () => {
    setMenuId(null);
    if (activeHistoryId === null && (prompt.trim() || code.trim() || draft)) {
      setCurrentSnap({ prompt, code, draft, validated });
    }
    setActiveHistoryId(null);
    setPrompt("");
    setCode("");
    setDraft(null);
    setValidated(false);
    setErr(null);
  };

  const onTogglePin = (id: string) => {
    updateHistory(
      history.map((h) =>
        h.id === id ? { ...h, pinned: !h.pinned } : h,
      ),
    );
    setMenuId(null);
  };

  const onDeleteOne = (id: string) => {
    updateHistory(history.filter((h) => h.id !== id));
    if (activeHistoryId === id) setActiveHistoryId(null);
    setMenuId(null);
  };

  const onCopy = async () => {
    if (!code.trim()) return;
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setErr("复制失败");
    }
  };

  const openSendModal = () => {
    if (!draft || !code.trim()) return;
    setSendFormErr(null);
    setSendName(draft.strategy_name || "");
    setSendDesc("");
    setSendOpen(true);
  };

  const confirmSendResearch = async () => {
    if (!draft || !code.trim()) return;
    const name = sendName.trim();
    if (!name) {
      setSendFormErr("请填写策略名称");
      return;
    }
    setSendBusy(true);
    setSendFormErr(null);
    setErr(null);
    try {
      const p = await createStrategyProjectFromCode({
        name,
        description: sendDesc.trim() || draft.description || name,
        strategyCode: code.trim(),
      });
      setSendOpen(false);
      openStrategyInNewTab(p.id);
    } catch (e) {
      setSendFormErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSendBusy(false);
    }
  };

  const canReturnCurrent = Boolean(currentSnap) && activeHistoryId !== null;
  const canSend = Boolean(draft && code.trim());

  return (
    <div className="flex min-h-[calc(100vh-4rem)] flex-col bg-[#f4f6fb] text-[15px] text-slate-800">
      <header className="border-b border-indigo-100/80 bg-white">
        <div className="mx-auto flex max-w-[1480px] items-center justify-between gap-3 px-5 py-3.5">
          <h1 className="flex items-center gap-2 text-lg font-bold text-slate-900">
            <LineChart className="h-5 w-5 text-indigo-600" />
            AI 策略生成
          </h1>
          <button
            type="button"
            disabled={busy || !prompt.trim()}
            onClick={() => void onGenerate()}
            className="inline-flex h-10 items-center gap-1.5 rounded-lg bg-indigo-600 px-5 text-[15px] font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Wand2 className="h-4 w-4" />
            )}
            {busy ? "生成中…" : "生成"}
          </button>
        </div>
      </header>

      <div className="mx-auto grid w-full max-w-[1480px] flex-1 grid-cols-1 lg:grid-cols-[280px_minmax(0,1fr)_minmax(0,1.15fr)]">
        {/* 历史侧栏靠左 */}
        <aside className="flex min-h-0 flex-col border-b border-slate-200 bg-[#eef0f7] lg:border-b-0 lg:border-r lg:border-indigo-100/80">
          <div className="space-y-2 p-3">
            <button
              type="button"
              onClick={onNewChat}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-indigo-200/80 bg-white px-3 py-2.5 text-[15px] font-medium text-slate-800 shadow-sm transition hover:bg-indigo-50/50"
            >
              <Plus className="h-4 w-4 text-indigo-600" />
              新策略草稿
            </button>
            {canReturnCurrent ? (
              <button
                type="button"
                onClick={onReturnCurrent}
                className="flex w-full items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-50"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                返回当前
              </button>
            ) : null}
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
            {grouped.length === 0 ? (
              <p className="px-2 py-6 text-center text-sm text-slate-400">
                暂无历史草稿
              </p>
            ) : null}
            {grouped.map(([label, items]) => (
              <div key={label} className="mb-3">
                <p className="px-2 py-1.5 text-xs font-medium text-slate-400">
                  {label}
                </p>
                <ul className="space-y-0.5">
                  {items.map((h) => {
                    const active = h.id === activeHistoryId;
                    return (
                      <li key={h.id} className="relative">
                        <div
                          className={`group flex items-start gap-1 rounded-lg px-2 py-2 ${
                            active
                              ? "bg-white shadow-sm ring-1 ring-indigo-100"
                              : "hover:bg-white/80"
                          }`}
                        >
                          <button
                            type="button"
                            onClick={() => onPickHistory(h)}
                            className="min-w-0 flex-1 text-left"
                          >
                            <p className="flex items-center gap-1 truncate text-[14px] font-semibold text-slate-800">
                              {h.pinned ? (
                                <Pin className="h-3 w-3 shrink-0 text-indigo-600" />
                              ) : null}
                              <span className="truncate font-mono text-[13px]">
                                {h.strategy_name}
                              </span>
                            </p>
                            <p className="mt-0.5 line-clamp-2 text-[13px] leading-snug text-slate-500">
                              {h.prompt}
                            </p>
                            <p className="mt-1 text-xs tabular-nums text-slate-400">
                              {fmtTime(h.at)}
                            </p>
                          </button>
                          <button
                            type="button"
                            title="更多"
                            onClick={(e) => {
                              e.stopPropagation();
                              setMenuId((cur) => (cur === h.id ? null : h.id));
                            }}
                            className={`mt-0.5 shrink-0 rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 ${
                              menuId === h.id
                                ? "bg-slate-100 text-slate-700 opacity-100"
                                : "opacity-0 group-hover:opacity-100"
                            }`}
                          >
                            <MoreHorizontal className="h-4 w-4" />
                          </button>
                        </div>
                        {menuId === h.id ? (
                          <div
                            ref={menuRef}
                            className="absolute right-2 top-9 z-20 w-36 overflow-hidden rounded-lg border border-slate-200 bg-white py-1 shadow-lg"
                          >
                            <button
                              type="button"
                              onClick={() => onTogglePin(h.id)}
                              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
                            >
                              <Pin className="h-3.5 w-3.5" />
                              {h.pinned ? "取消置顶" : "置顶"}
                            </button>
                            <button
                              type="button"
                              onClick={() => onDeleteOne(h.id)}
                              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-rose-600 hover:bg-rose-50"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                              删除
                            </button>
                          </div>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        </aside>

        {/* 提问 */}
        <section className="flex min-h-0 flex-col border-b border-slate-200 bg-white lg:border-b-0 lg:border-r">
          <div className="flex h-11 items-center border-b border-indigo-50 px-4">
            <p className="text-[15px] font-semibold text-slate-800">研究假设</p>
          </div>
          <div className="flex min-h-0 flex-1 flex-col p-4">
            <textarea
              value={prompt}
              maxLength={PROMPT_MAX}
              onChange={(e) => {
                setPrompt(e.target.value.slice(0, PROMPT_MAX));
                setErr(null);
                if (activeHistoryId !== null) {
                  setActiveHistoryId(null);
                  setCurrentSnap(null);
                }
              }}
              onKeyDown={(e) => {
                if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !busy) {
                  e.preventDefault();
                  void onGenerate();
                }
              }}
              placeholder="描述选股逻辑、调仓周期与目标权重方式…（如：每 20 日调仓，买入过去 20 日动量最高 30 只，等权）"
              className="min-h-[300px] flex-1 resize-none rounded-xl border border-slate-200 bg-[#f8f9fc] px-4 py-3.5 text-[15px] leading-7 outline-none focus:border-indigo-500 focus:bg-white focus:ring-1 focus:ring-indigo-500"
            />
            {err ? (
              <p className="mt-2 text-sm text-rose-600">{err}</p>
            ) : null}
          </div>
        </section>

        {/* 代码 */}
        <section className="flex min-h-0 flex-col bg-white">
          <div className="flex h-11 items-center justify-between gap-2 border-b border-indigo-50 px-4">
            <div className="min-w-0">
              <p className="truncate text-[15px] font-semibold text-slate-800">
                {draft ? draft.strategy_name : "策略代码"}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {validated && draft ? (
                <span className="hidden rounded border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700 sm:inline">
                  AI 已校验
                </span>
              ) : draft && !validated ? (
                <span className="hidden rounded border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 sm:inline">
                  已编辑
                </span>
              ) : null}
              <button
                type="button"
                disabled={!code.trim()}
                onClick={() => void onCopy()}
                className="inline-flex h-9 items-center gap-1 rounded-lg border border-slate-200 px-3 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-40"
              >
                <Copy className="h-4 w-4" />
                {copied ? "已复制" : "复制"}
              </button>
              <button
                type="button"
                disabled={!canSend || sendBusy}
                onClick={openSendModal}
                className="inline-flex h-9 items-center gap-1 rounded-lg bg-indigo-600 px-3 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-40"
              >
                <LineChart className="h-4 w-4" />
                送研究
              </button>
            </div>
          </div>
          {draft?.description ||
          (draft?.warnings && draft.warnings.length > 0) ? (
            <div className="space-y-1 border-b border-indigo-50 px-4 py-2 text-xs text-slate-500">
              {draft.description ? (
                <p className="line-clamp-2">{draft.description}</p>
              ) : null}
              {draft.warnings?.length ? (
                <p className="text-amber-700">
                  提示：{draft.warnings.join("；")}
                </p>
              ) : null}
            </div>
          ) : null}
          <div className="min-h-0 flex-1 p-4">
            {busy ? (
              <div className="flex h-full min-h-[300px] items-center justify-center rounded-xl border border-slate-200">
                <Loader2 className="h-7 w-7 animate-spin text-indigo-600" />
              </div>
            ) : (
              <FactorCodeEditor
                value={code}
                height="100%"
                variant="dark"
                className="h-[min(70vh,560px)] min-h-[300px]"
                onChange={(v) => {
                  setCode(v);
                  setValidated(false);
                  if (activeHistoryId !== null) {
                    setActiveHistoryId(null);
                    setCurrentSnap(null);
                  }
                }}
              />
            )}
          </div>
        </section>
      </div>

      {sendOpen ? (
        <div className="fixed inset-0 z-[130] flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-5 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-bold text-slate-900">送到策略研究</h3>
              <button
                type="button"
                onClick={() => setSendOpen(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            {!validated ? (
              <p className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                代码已手动修改，不再视为 AI 端点校验通过。
              </p>
            ) : null}
            <div className="space-y-3 text-[15px]">
              <label className="block text-sm text-slate-500">
                策略名称
                <input
                  value={sendName}
                  onChange={(e) => {
                    setSendName(e.target.value);
                    setSendFormErr(null);
                  }}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 font-mono text-[15px] outline-none focus:border-indigo-400"
                />
              </label>
              <label className="block text-sm text-slate-500">
                <span className="flex items-center justify-between gap-2">
                  <span>说明（可选）</span>
                  <span className="tabular-nums text-slate-400">
                    {sendDesc.length}/{DESC_MAX}
                  </span>
                </span>
                <input
                  value={sendDesc}
                  maxLength={DESC_MAX}
                  onChange={(e) => {
                    setSendDesc(e.target.value.slice(0, DESC_MAX));
                    setSendFormErr(null);
                  }}
                  placeholder="留空则用生成说明"
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-[15px] outline-none focus:border-indigo-400"
                />
              </label>
              {sendFormErr ? (
                <p className="text-sm text-red-600">{sendFormErr}</p>
              ) : null}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setSendOpen(false)}
                className="rounded-lg border border-slate-200 px-4 py-2.5 text-[15px] text-slate-600 hover:bg-slate-50"
              >
                取消
              </button>
              <button
                type="button"
                disabled={sendBusy}
                onClick={() => void confirmSendResearch()}
                className="rounded-lg bg-indigo-600 px-5 py-2.5 text-[15px] font-semibold text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {sendBusy ? "处理中…" : "确定"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
