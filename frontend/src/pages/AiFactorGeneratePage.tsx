import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Copy,
  FlaskConical,
  Loader2,
  Menu,
  MoreHorizontal,
  Pin,
  Plus,
  Sparkles,
  Trash2,
  Wand2,
  X,
} from "lucide-react";
import { FactorCodeEditor } from "@/components/FactorCodeEditor";
import { AiFactorExplanation } from "@/components/AiFactorExplanation";
import { factorPromptError, factorRejectionMessage } from "@/lib/aiFactorFeedback";
import { factorNameError } from "@/lib/factorName";
import {
  ygGenerateFactorDraft,
  type AiFactorDraft,
} from "@/lib/aiFactorApi";
import {
  createDetectProjectFromSnippet,
  openDetectPlaceholderTab,
  navigateDetectTab,
} from "@/lib/detectStore";
import {
  builtinCategoryLabelsFromFactors,
  loadFactors,
} from "@/lib/factorCatalog";
import { listAllUserLibraryFactors } from "@/lib/userFactorLibraries";
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
  factor_name: string;
  factor_code: string;
  description: string;
  assumptions?: string[];
  warnings?: string[];
  pinned?: boolean;
};

type WorkspaceSnap = {
  prompt: string;
  code: string;
  draft: AiFactorDraft | null;
};

function newIdempotencyKey() {
  return newUuidV4();
}

function loadHistory(): HistoryItem[] {
  try {
    const key = aiHistoryStorageKey("factor");
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
    const key = aiHistoryStorageKey("factor");
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

export function AiFactorGeneratePage() {
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [draft, setDraft] = useState<AiFactorDraft | null>(null);
  const [code, setCode] = useState("");
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
  const [sendCategory, setSendCategory] = useState("");
  const [sendFormErr, setSendFormErr] = useState<string | null>(null);
  const [categoryOptions, setCategoryOptions] = useState<string[]>(["其他"]);
  const [takenNames, setTakenNames] = useState<Set<string>>(() => new Set());
  const [historyOpen, setHistoryOpen] = useState(false);
  const [isNarrow, setIsNarrow] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    const m = window.matchMedia("(max-width: 1023px)");
    const sync = () => setIsNarrow(m.matches);
    sync();
    m.addEventListener("change", sync);
    return () => m.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    return subscribeAuth(() => {
      setHistory(sortHistory(loadHistory()));
      setActiveHistoryId(null);
      setCurrentSnap(null);
      setPrompt("");
      setCode("");
      setDraft(null);
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
    const inputError = factorPromptError(text);
    if (inputError) {
      setValidationErrors([]);
      setErr(inputError);
      return;
    }
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setBusy(true);
    setErr(null);
    setValidationErrors([]);
    setDraft(null);
    setCode("");
    try {
      const data = await ygGenerateFactorDraft(
        {
          prompt: text,
          idempotency_key: newIdempotencyKey(),
          context: { universe: "CSI500", frequency: "1d" },
        },
        ac.signal,
      );
      if (data.status !== "ready" || data.validation?.status !== "passed" || !data.factor?.factor_code?.trim()) {
        const errs = data.validation?.errors || [];
        setDraft(null);
        setCode("");
        setValidationErrors(errs);
        setErr(factorRejectionMessage(errs));
        return;
      }
      const id = data.generation_id || newIdempotencyKey();
      setDraft(data.factor);
      setCode(data.factor.factor_code);
      setActiveHistoryId(id);
      setCurrentSnap(null);
      pushHistory({
        id,
        prompt: text,
        at: Date.now(),
        factor_name: data.factor.factor_name,
        factor_code: data.factor.factor_code,
        description: data.factor.description || "",
        assumptions: data.factor.assumptions || [],
        warnings: data.factor.warnings || [],
      });
      setHistoryOpen(false);
    } catch (e) {
      if ((e as Error)?.name === "AbortError") return;
      setDraft(null);
      setCode("");
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [prompt]);

  const onPickHistory = (h: HistoryItem) => {
    setMenuId(null);
    if (h.id === activeHistoryId) {
      setHistoryOpen(false);
      return;
    }
    if (activeHistoryId === null && (prompt.trim() || code.trim() || draft)) {
      setCurrentSnap({ prompt, code, draft });
    }
    setActiveHistoryId(h.id);
    setPrompt(h.prompt);
    setCode(h.factor_code);
    setDraft({
      factor_name: h.factor_name,
      factor_code: h.factor_code,
      description: h.description,
      used_fields: [],
      used_library_methods: [],
      assumptions: h.assumptions || [],
      warnings: h.warnings || [],
    });
    setErr(null);
    setHistoryOpen(false);
  };

  const onReturnCurrent = () => {
    if (!currentSnap) return;
    setMenuId(null);
    setActiveHistoryId(null);
    setPrompt(currentSnap.prompt);
    setCode(currentSnap.code);
    setDraft(currentSnap.draft);
    setErr(null);
    setHistoryOpen(false);
  };

  const onNewChat = () => {
    setMenuId(null);
    if (activeHistoryId === null && (prompt.trim() || code.trim() || draft)) {
      setCurrentSnap({ prompt, code, draft });
    }
    setActiveHistoryId(null);
    setPrompt("");
    setCode("");
    setDraft(null);
    setErr(null);
    setHistoryOpen(false);
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
    setSendName(draft.factor_name || "");
    setSendDesc("");
    setSendCategory("");
    setSendOpen(true);
    void Promise.all([
      loadFactors(true).catch(() => []),
      listAllUserLibraryFactors().catch(() => []),
    ]).then(([fs, userRows]) => {
      const cats = builtinCategoryLabelsFromFactors(
        fs.filter((f) => f.library !== "custom_lib"),
      );
      setCategoryOptions([...cats, "其他"]);
      const taken = new Set<string>();
      for (const f of fs) {
        if (f.library === "custom_lib") continue;
        taken.add(f.name);
        if (f.methodName) taken.add(f.methodName);
      }
      for (const r of userRows) taken.add(r.name);
      setTakenNames(taken);
      const n = (draft.factor_name || "").trim();
      if (n && taken.has(n)) {
        setSendFormErr(`「${n}」与内置或已有因子库重名，请改名后再确定`);
      }
    });
  };

  const confirmSendDetect = async () => {
    if (!draft || !code.trim()) return;
    const name = sendName.trim();
    const description = sendDesc.trim();
    const category = sendCategory.trim();
    const nameError = factorNameError(name);
    if (nameError) {
      setSendFormErr(nameError);
      return;
    }
    if (takenNames.has(name)) {
      setSendFormErr(`「${name}」与内置或已有因子库重名，请改名后再确定`);
      return;
    }
    if (!description) {
      setSendFormErr("请填写中文解释");
      return;
    }
    if (!category) {
      setSendFormErr("请选择分类");
      return;
    }
    setSendBusy(true);
    setSendFormErr(null);
    setErr(null);
    const tab = openDetectPlaceholderTab();
    try {
      const p = await createDetectProjectFromSnippet({
        title: description,
        code: code.trim(),
        name,
        description,
        category,
      });
      setSendOpen(false);
      navigateDetectTab(tab, p.id, p);
    } catch (e) {
      try {
        tab?.close();
      } catch {
        /* ignore */
      }
      setSendFormErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSendBusy(false);
    }
  };

  const canReturnCurrent = Boolean(currentSnap) && activeHistoryId !== null;

  const onPromptChange = (value: string) => {
    setPrompt(value.slice(0, PROMPT_MAX));
    setErr(null);
    if (activeHistoryId !== null) {
      setActiveHistoryId(null);
      setCurrentSnap(null);
    }
  };

  const historyPanel = (
    <>
      <div className="space-y-2 p-3">
        <button
          type="button"
          onClick={onNewChat}
          className="flex w-full items-center justify-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-2.5 text-[15px] font-medium text-slate-800 shadow-sm transition hover:bg-slate-50"
        >
          <Plus className="h-4 w-4" />
          开启新问答
        </button>
        {canReturnCurrent ? (
          <button
            type="button"
            onClick={onReturnCurrent}
            className="flex w-full items-center justify-center gap-1.5 rounded-full px-3 py-2 text-sm font-medium text-teal-700 hover:bg-teal-50"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            返回当前
          </button>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {grouped.length === 0 ? (
          <p className="px-2 py-6 text-center text-sm text-slate-400">
            暂无历史记录
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
                      className={`group flex items-start gap-1 rounded-xl px-2 py-2 ${
                        active ? "bg-white shadow-sm" : "hover:bg-white/70"
                      }`}
                    >
                      <button
                        type="button"
                        onClick={() => onPickHistory(h)}
                        className="min-w-0 flex-1 text-left"
                      >
                        <p className="flex items-center gap-1 truncate text-[14px] font-semibold text-slate-800">
                          {h.pinned ? (
                            <Pin className="h-3 w-3 shrink-0 text-teal-600" />
                          ) : null}
                          <span className="truncate font-mono text-[13px]">
                            {h.factor_name}
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
                        className={`mt-0.5 shrink-0 rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 ${
                          menuId === h.id
                            ? "bg-slate-100 text-slate-700 opacity-100"
                            : "opacity-100 lg:opacity-0 lg:group-hover:opacity-100"
                        }`}
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </button>
                    </div>
                    {menuId === h.id ? (
                      <div
                        ref={menuRef}
                        className="absolute right-2 top-9 z-20 w-36 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-lg"
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
    </>
  );

  return (
    <div className="flex min-h-[calc(100vh-4rem)] flex-col bg-[#f7f8fa] text-[15px] text-slate-800 lg:h-[calc(100vh-4rem)]">
      {/* PC 顶栏 */}
      <header className="hidden shrink-0 border-b border-slate-200/80 bg-white lg:block">
        <div className="mx-auto flex max-w-[1480px] items-center justify-between gap-2 px-5 py-3.5">
          <h1 className="flex min-w-0 items-center gap-2 text-lg font-bold text-slate-900">
            <Sparkles className="h-5 w-5 shrink-0 text-teal-600" />
            <span className="truncate">AI 因子生成</span>
          </h1>
          <button
            type="button"
            disabled={busy || !prompt.trim()}
            onClick={() => void onGenerate()}
            className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-xl bg-teal-700 px-5 text-[15px] font-semibold text-white hover:bg-teal-800 disabled:opacity-50"
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

      {/* 手机顶栏：左汉堡开历史 */}
      <header className="relative flex shrink-0 items-center justify-center border-b border-slate-200/80 bg-white px-12 py-2.5 lg:hidden">
        <button
          type="button"
          aria-label="历史记录"
          onClick={() => setHistoryOpen(true)}
          className="absolute left-2 rounded-lg p-2 text-slate-700 hover:bg-slate-100"
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="min-w-0 text-center">
          <h1 className="truncate text-base font-bold text-slate-900">
            AI 因子生成
          </h1>
          <p className="text-[11px] leading-tight text-slate-400">
            AI 生成可能有误，请核实
          </p>
        </div>
      </header>

      {isNarrow && historyOpen ? (
        <div className="fixed inset-0 z-[120] lg:hidden">
          <button
            type="button"
            aria-label="关闭历史"
            className="absolute inset-0 bg-slate-900/40"
            onClick={() => setHistoryOpen(false)}
          />
          <aside className="absolute inset-y-0 left-0 flex w-[min(86vw,320px)] flex-col bg-[#f0f2f5] shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-200/80 px-3 py-2.5">
              <p className="text-[15px] font-semibold text-slate-800">历史记录</p>
              <button
                type="button"
                aria-label="关闭"
                onClick={() => setHistoryOpen(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            {historyPanel}
          </aside>
        </div>
      ) : null}

      <div className="mx-auto grid min-h-0 w-full max-w-[1480px] flex-1 grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)_minmax(0,1.15fr)]">
        {!isNarrow ? (
          <aside className="hidden min-h-0 flex-col border-r border-slate-200/80 bg-[#f0f2f5] lg:flex">
            {historyPanel}
          </aside>
        ) : null}

        {/* PC 提问 */}
        <section className="hidden min-h-0 flex-col border-r border-slate-200 bg-white lg:flex">
          <div className="flex h-11 items-center border-b border-slate-100 px-4">
            <p className="text-[15px] font-semibold text-slate-800">提问</p>
          </div>
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4">
            <textarea
              value={prompt}
              maxLength={PROMPT_MAX}
              onChange={(e) => onPromptChange(e.target.value)}
              onKeyDown={(e) => {
                if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !busy) {
                  e.preventDefault();
                  void onGenerate();
                }
              }}
              placeholder="用自然语言描述你想要的因子逻辑…"
              className="min-h-[300px] flex-1 resize-none rounded-2xl border border-slate-200 bg-slate-50/60 px-4 py-3.5 text-[15px] leading-7 outline-none focus:border-teal-500 focus:bg-white focus:ring-1 focus:ring-teal-500"
            />
            <div className="mt-2 flex flex-col gap-1.5">
              <p className="text-xs text-slate-400">Ctrl+Enter 生成</p>
            </div>
            {err ? (
              <div role="alert" className="mt-2 text-sm text-rose-600">
                <p>{err}</p>
                {validationErrors.length > 0 && <details className="mt-2"><summary>错误详情</summary><p className="whitespace-pre-wrap">{validationErrors.join("；")}</p></details>}
              </div>
            ) : null}
          </div>
        </section>

        {/* PC 代码 */}
        <section className="hidden min-h-0 flex-col bg-white lg:flex">
          <div className="flex h-11 items-center justify-between gap-2 border-b border-slate-100 px-4">
            <p className="truncate text-[15px] font-semibold text-slate-800">
              {draft ? draft.factor_name : "生成代码"}
            </p>
            <div className="flex shrink-0 items-center gap-2">
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
                disabled={!draft || !code.trim() || sendBusy}
                onClick={openSendModal}
                className="inline-flex h-9 items-center gap-1 rounded-lg bg-teal-700 px-3 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-40"
              >
                <FlaskConical className="h-4 w-4" />
                送检测
              </button>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {!busy && draft && <AiFactorExplanation draft={draft} />}
            {busy ? (
              <div className="flex h-full min-h-[300px] items-center justify-center rounded-2xl border border-slate-200">
                <Loader2 className="h-7 w-7 animate-spin text-teal-700" />
              </div>
            ) : (
              <FactorCodeEditor
                value={code}
                height="100%"
                variant="dark"
                className="h-[min(70vh,560px)] min-h-[300px]"
                onChange={(v) => {
                  setCode(v);
                  if (activeHistoryId !== null) {
                    setActiveHistoryId(null);
                    setCurrentSnap(null);
                  }
                }}
              />
            )}
          </div>
        </section>

        {/* 手机：豆包式主区 + 底栏 */}
        <div className="flex min-h-0 flex-1 flex-col bg-white lg:hidden">
          <div className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
            {!busy && !code && !err ? (
              <div className="flex h-full min-h-[40vh] flex-col items-center justify-center px-4 text-center">
                <Sparkles className="mb-3 h-8 w-8 text-teal-600/80" />
                <p className="text-base font-semibold text-slate-800">
                  描述你想要的因子
                </p>
              </div>
            ) : null}

            {prompt.trim() && (busy || code || err) ? (
              <div className="mb-3 flex justify-end">
                <div className="max-w-[88%] rounded-2xl rounded-br-md bg-teal-700 px-3.5 py-2.5 text-[15px] leading-6 text-white">
                  {prompt}
                </div>
              </div>
            ) : null}

            {busy ? (
              <div className="rounded-2xl bg-slate-100 px-4 py-8 text-center">
                <Loader2 className="mx-auto h-6 w-6 animate-spin text-teal-700" />
                <p className="mt-2 text-sm text-slate-500">正在生成…</p>
              </div>
            ) : null}

            {err && !busy ? (
              <div role="alert" className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-600">
                <p>{err}</p>
                {validationErrors.length > 0 && <details className="mt-2"><summary>错误详情</summary><p className="whitespace-pre-wrap">{validationErrors.join("；")}</p></details>}
              </div>
            ) : null}

            {!busy && code ? (
              <div className="overflow-hidden rounded-2xl bg-slate-100">
                <div className="flex items-center justify-between gap-2 border-b border-slate-200/80 px-3 py-2.5">
                  <p className="min-w-0 truncate text-sm font-semibold text-slate-800">
                    {draft?.factor_name || "生成代码"}
                  </p>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <button
                      type="button"
                      disabled={!code.trim()}
                      onClick={() => void onCopy()}
                      className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 text-xs text-slate-700 disabled:opacity-40"
                    >
                      <Copy className="h-3.5 w-3.5" />
                      {copied ? "已复制" : "复制"}
                    </button>
                    <button
                      type="button"
                      disabled={!draft || !code.trim() || sendBusy}
                      onClick={openSendModal}
                      className="inline-flex h-8 items-center gap-1 rounded-lg bg-teal-700 px-2.5 text-xs font-semibold text-white disabled:opacity-40"
                    >
                      <FlaskConical className="h-3.5 w-3.5" />
                      送检测
                    </button>
                  </div>
                </div>
                {draft && <AiFactorExplanation draft={draft} />}
                <div className="p-2">
                  <FactorCodeEditor
                    value={code}
                    height="100%"
                    variant="dark"
                    className="h-[min(52vh,420px)] min-h-[220px]"
                    onChange={(v) => {
                      setCode(v);
                      if (activeHistoryId !== null) {
                        setActiveHistoryId(null);
                        setCurrentSnap(null);
                      }
                    }}
                  />
                </div>
              </div>
            ) : null}
          </div>

          <div className="shrink-0 border-t border-slate-200/80 bg-white px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2">
            <div className="flex items-end gap-2 rounded-[22px] border border-slate-200 bg-slate-50 px-2 py-1.5">
              <textarea
                value={prompt}
                maxLength={PROMPT_MAX}
                rows={1}
                onChange={(e) => onPromptChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !busy) {
                    e.preventDefault();
                    void onGenerate();
                  }
                }}
                placeholder="描述因子逻辑…"
                className="max-h-28 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-[15px] leading-5 outline-none"
              />
              <button
                type="button"
                disabled={busy || !prompt.trim()}
                onClick={() => void onGenerate()}
                className="mb-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-teal-700 text-white hover:bg-teal-800 disabled:opacity-40"
                aria-label="发送"
              >
                {busy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Wand2 className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      {sendOpen ? (
        <div className="fixed inset-0 z-[130] flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-bold text-slate-900">送到因子检测</h3>
              <button
                type="button"
                onClick={() => setSendOpen(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-3 text-[15px]">
              <label className="block text-sm text-slate-500">
                因子代码名
                <input
                  value={sendName}
                  onChange={(e) => {
                    setSendName(e.target.value);
                    const n = e.target.value.trim();
                    if (n && takenNames.has(n)) {
                      setSendFormErr(
                        `「${n}」与内置或已有因子库重名，请改名后再确定`,
                      );
                    } else if (sendFormErr?.includes("重名")) {
                      setSendFormErr(null);
                    }
                  }}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 font-mono text-[15px] outline-none focus:border-teal-400"
                />
              </label>
              <label className="block text-sm text-slate-500">
                <span className="flex items-center justify-between gap-2">
                  <span>中文解释（检测名称）</span>
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
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-[15px] outline-none focus:border-teal-400"
                />
              </label>
              <label className="block text-sm text-slate-500">
                分类
                <select
                  value={sendCategory}
                  onChange={(e) => {
                    setSendCategory(e.target.value);
                    setSendFormErr(null);
                  }}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-[15px] outline-none focus:border-teal-400"
                >
                  <option value="">请选择</option>
                  {categoryOptions.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
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
                onClick={() => void confirmSendDetect()}
                className="rounded-lg bg-teal-700 px-5 py-2.5 text-[15px] font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
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
