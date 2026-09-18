import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  ChevronDown,
  ExternalLink,
  History,
  Loader2,
  Lightbulb,
  Newspaper,
  Sparkles,
  Square,
  X,
} from "lucide-react";
import { runGather, type EvidencePack } from "@/lib/gatherApi";
import {
  loadGatherHistory,
  loadLastGatherPack,
  pushGatherHistory,
  setActivePackForIdea,
  type GatherHistoryEntry,
} from "@/lib/gatherHistory";
import { fetchNewsDict } from "@/lib/newsApi";

const PRESETS = [
  {
    label: "异象有效性",
    topic: "经典股票异象这几年还有效吗？有没有明显衰减或风格切换？",
    themes: [],
  },
  {
    label: "量价讨论",
    topic: "最近 A 股量价选股在讨论什么？哪些还值得拿去检验？",
    themes: [],
  },
  {
    label: "流动与波动",
    topic: "流动性和波动相关的研究，现在市场和学术分别怎么看？",
    themes: [],
  },
  {
    label: "换手反转",
    topic: "换手率与短期反转在 A 股近五年是否仍然有效？",
    themes: [],
  },
];

const COUNT_OPTIONS = [8, 12, 20, 30, 40, 50] as const;

type TimePreset =
  | "7d"
  | "14d"
  | "30d"
  | "60d"
  | "90d"
  | "180d"
  | "1y"
  | "2y"
  | "3y"
  | "5y"
  | "10y"
  | "all";

const TIME_OPTIONS: { value: TimePreset; label: string }[] = [
  { value: "7d", label: "近 7 日" },
  { value: "14d", label: "近 14 日" },
  { value: "30d", label: "近 30 日" },
  { value: "60d", label: "近 60 日" },
  { value: "90d", label: "近 90 日" },
  { value: "180d", label: "近半年" },
  { value: "1y", label: "近 1 年" },
  { value: "2y", label: "近 2 年" },
  { value: "3y", label: "近 3 年" },
  { value: "5y", label: "近 5 年" },
  { value: "10y", label: "近 10 年" },
  { value: "all", label: "不限（偏长文献）" },
];

function newsHref(id: number | string) {
  return `/news/${id}?from=gather`;
}

export function AgentGatherPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const abortRef = useRef<AbortController | null>(null);
  const themeBoxRef = useRef<HTMLDivElement | null>(null);

  const [topic, setTopic] = useState(PRESETS[0].topic);
  const [selectedThemes, setSelectedThemes] = useState<string[]>(
    PRESETS[0].themes,
  );
  const [themeOptions, setThemeOptions] = useState<string[]>([]);
  const [themeOpen, setThemeOpen] = useState(false);
  const [preset, setPreset] = useState<TimePreset>("3y");
  const [maxItems, setMaxItems] = useState<number>(20);
  const [useLlm, setUseLlm] = useState(true);
  const [srcNews, setSrcNews] = useState(true);
  const [srcReport, setSrcReport] = useState(true);
  const [srcPaper, setSrcPaper] = useState(true);
  const [srcPost, setSrcPost] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [pack, setPack] = useState<EvidencePack | null>(() =>
    loadLastGatherPack(),
  );
  const [history, setHistory] = useState<GatherHistoryEntry[]>(() =>
    loadGatherHistory(),
  );
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    void fetchNewsDict()
      .then((d) => setThemeOptions(d.themes || []))
      .catch(() => setThemeOptions([]));
  }, []);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!themeBoxRef.current?.contains(e.target as Node)) setThemeOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  useEffect(() => {
    const pid = searchParams.get("pack");
    if (!pid) return;
    const hit = loadGatherHistory().find((h) => h.pack_id === pid);
    if (hit) {
      setPack(hit.pack);
      setTopic(hit.topic);
      setSelectedThemes(hit.themes || []);
      setPreset((hit.preset as TimePreset) || "3y");
      setMaxItems(hit.max_items || 20);
    }
  }, [searchParams]);

  const themeLabel = useMemo(() => {
    if (!selectedThemes.length) return "不限题材（可不选）";
    if (selectedThemes.length <= 3) return selectedThemes.join("、");
    return `${selectedThemes.slice(0, 3).join("、")} 等${selectedThemes.length}个`;
  }, [selectedThemes]);

  const toggleTheme = (t: string) => {
    setSelectedThemes((prev) =>
      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t].slice(0, 8),
    );
  };

  const modeLabel = useMemo(() => {
    const m = pack?.stats?.digest_mode || pack?.query?.digest_mode;
    if (m === "llm") return "LLM 摘要";
    if (m === "rule_fallback") return "规则回退";
    if (m === "rule_forced") return "仅规则";
    if (m === "rule") return "规则摘要";
    return m ? String(m) : "—";
  }, [pack]);

  const statusLabel = busy ? "Running" : pack ? "Ready" : "Idle";
  const step = !topic.trim() ? 1 : busy ? 2 : pack ? 3 : 2;

  const onCancel = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setErr("已取消搜集");
  };

  const onRun = async () => {
    const t = topic.trim();
    if (!t) {
      setErr("请先填写研究问题");
      return;
    }
    if (!srcNews && !srcReport && !srcPaper && !srcPost) {
      setErr("请至少选择一个在线来源");
      return;
    }
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setBusy(true);
    setErr(null);
    try {
      const themeList = [...selectedThemes];
      const data = await runGather(
        {
          topic: t,
          themes: themeList,
          time_window: { preset },
          max_items: maxItems,
          sources: {
            news: srcNews,
            report: srcReport,
            paper: srcPaper,
            post: srcPost,
          },
          use_llm: useLlm,
        },
        ac.signal,
      );
      setPack(data);
      const entry: GatherHistoryEntry = {
        pack_id: data.pack_id,
        topic: t,
        themes: themeList,
        preset,
        max_items: maxItems,
        finishedAt: new Date().toISOString(),
        digest_mode: data.stats?.digest_mode,
        returned: data.stats?.returned ?? data.items?.length,
        pack: data,
      };
      pushGatherHistory(entry);
      setHistory(loadGatherHistory());
      setSearchParams({ pack: data.pack_id }, { replace: true });
    } catch (e) {
      if (ac.signal.aborted) return;
      setPack(null);
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      if (abortRef.current === ac) abortRef.current = null;
      setBusy(false);
    }
  };

  const openHistory = (h: GatherHistoryEntry) => {
    setPack(h.pack);
    setTopic(h.topic);
    setSelectedThemes(h.themes || []);
    setPreset((h.preset as TimePreset) || "3y");
    setMaxItems(h.max_items || 20);
    setShowHistory(false);
    setSearchParams({ pack: h.pack_id }, { replace: true });
  };

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-[#f0f3f8] text-slate-800 lg:flex-row">
      <aside className="flex max-h-[48vh] w-full shrink-0 flex-col border-b border-slate-200/90 bg-white lg:max-h-none lg:h-full lg:w-[20.5rem] lg:border-b-0 lg:border-r xl:w-[22rem]">
        <div className="flex items-center gap-3 border-b border-slate-100 px-5 py-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600">
            <Newspaper className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-base font-semibold text-slate-900">
              信息搜集 Agent
            </div>
            <div className="text-sm text-slate-500">自然语言问题 · 在线资料汇总</div>
          </div>
          <button
            type="button"
            title="本机历史"
            onClick={() => setShowHistory((v) => !v)}
            className={`rounded-lg p-2 ${
              showHistory
                ? "bg-emerald-50 text-emerald-700"
                : "text-slate-400 hover:bg-slate-50 hover:text-slate-700"
            }`}
          >
            <History className="h-4 w-4" />
          </button>
        </div>

        {showHistory ? (
          <div className="flex flex-1 flex-col overflow-y-auto px-4 py-3">
            <div className="mb-2 text-sm font-medium text-slate-700">
              本次会话历史
            </div>
            {history.length === 0 ? (
              <p className="text-sm text-slate-400">
                暂无记录，搜集一次后会出现在这里。
              </p>
            ) : (
              <ul className="space-y-2">
                {history.map((h) => (
                  <li key={h.pack_id}>
                    <button
                      type="button"
                      onClick={() => openHistory(h)}
                      className="w-full rounded-xl border border-slate-100 bg-slate-50 px-3 py-2.5 text-left hover:border-emerald-200 hover:bg-emerald-50/50"
                    >
                      <div className="line-clamp-2 text-sm font-medium text-slate-800">
                        {h.topic}
                      </div>
                      <div className="mt-1 text-xs text-slate-400">
                        {h.returned ?? "—"} 条 ·{" "}
                        {h.finishedAt.slice(0, 16).replace("T", " ")}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : (
          <>
            <div className="border-b border-slate-100 px-5 py-3">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                进度 · {step}/3
              </div>
              <ol className="mt-2 space-y-1.5 text-sm">
                {[
                  { n: 1, t: "输入问题" },
                  { n: 2, t: "检索在线资料" },
                  { n: 3, t: "汇总概括" },
                ].map((s) => (
                  <li
                    key={s.n}
                    className={`flex items-center gap-2 ${
                      step >= s.n ? "text-slate-800" : "text-slate-400"
                    }`}
                  >
                    <span
                      className={`h-2 w-2 rounded-full ${
                        step === s.n
                          ? "bg-emerald-500"
                          : step > s.n
                            ? "bg-emerald-300"
                            : "bg-slate-300"
                      }`}
                    />
                    {s.t}
                  </li>
                ))}
              </ol>
            </div>

            <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-5 py-4">
              <div>
                <label className="block text-sm font-medium text-slate-700">
                  研究问题（自然语言）
                </label>
                <textarea
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  rows={4}
                  maxLength={240}
                  className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2.5 text-sm outline-none focus:border-emerald-300 focus:bg-white focus:ring-2 focus:ring-emerald-100"
                  placeholder="例如：经典股票异象这几年还有效吗？有没有明显衰减或风格切换？"
                />
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {PRESETS.map((p) => (
                    <button
                      key={p.label}
                      type="button"
                      onClick={() => {
                        setTopic(p.topic);
                        setSelectedThemes(p.themes);
                      }}
                      className="rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-emerald-50 hover:text-emerald-700"
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <div className="text-sm font-medium text-slate-700">在线来源</div>
                <div className="mt-2 grid grid-cols-2 gap-2 text-sm text-slate-700">
                  {(
                    [
                      ["资讯", srcNews, setSrcNews],
                      ["研报", srcReport, setSrcReport],
                      ["论文", srcPaper, setSrcPaper],
                      ["帖子", srcPost, setSrcPost],
                    ] as const
                  ).map(([label, on, set]) => (
                    <label key={label} className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={on}
                        onChange={(e) => set(e.target.checked)}
                        className="rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                      />
                      {label}
                    </label>
                  ))}
                </div>
              </div>

              <div ref={themeBoxRef} className="relative">
                <div className="flex items-center justify-between gap-2">
                  <label className="block text-sm font-medium text-slate-700">
                    题材标签
                  </label>
                  {selectedThemes.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setSelectedThemes([])}
                      className="text-xs text-slate-400 hover:text-slate-700"
                    >
                      清空
                    </button>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => setThemeOpen((v) => !v)}
                  className="mt-2 flex w-full items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-left text-sm hover:border-emerald-300"
                >
                  <span
                    className={
                      selectedThemes.length
                        ? "text-slate-800"
                        : "text-slate-400"
                    }
                  >
                    {themeLabel}
                  </span>
                  <ChevronDown
                    className={`h-4 w-4 shrink-0 text-slate-400 transition ${themeOpen ? "rotate-180" : ""}`}
                  />
                </button>
                {selectedThemes.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {selectedThemes.map((t) => (
                      <span
                        key={t}
                        className="inline-flex items-center gap-1 rounded-lg bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-800"
                      >
                        {t}
                        <button
                          type="button"
                          onClick={() => toggleTheme(t)}
                          className="rounded hover:bg-emerald-100"
                          aria-label={`移除 ${t}`}
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}
                {themeOpen && (
                  <div className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-xl border border-slate-200 bg-white py-1 shadow-lg">
                    {themeOptions.length === 0 ? (
                      <div className="px-3 py-2 text-sm text-slate-400">
                        题材字典加载中…
                      </div>
                    ) : (
                      themeOptions.map((t) => {
                        const on = selectedThemes.includes(t);
                        return (
                          <button
                            key={t}
                            type="button"
                            onClick={() => toggleTheme(t)}
                            className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-slate-50 ${
                              on ? "bg-emerald-50/80 text-emerald-900" : "text-slate-700"
                            }`}
                          >
                            <span
                              className={`flex h-4 w-4 items-center justify-center rounded border text-[10px] ${
                                on
                                  ? "border-emerald-500 bg-emerald-500 text-white"
                                  : "border-slate-300"
                              }`}
                            >
                              {on ? "✓" : ""}
                            </span>
                            {t}
                          </button>
                        );
                      })
                    )}
                  </div>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-slate-700">
                    时间窗
                  </label>
                  <select
                    value={preset}
                    onChange={(e) => setPreset(e.target.value as TimePreset)}
                    className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm"
                  >
                    {TIME_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700">
                    条数
                  </label>
                  <select
                    value={maxItems}
                    onChange={(e) => setMaxItems(Number(e.target.value))}
                    className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm"
                  >
                    {COUNT_OPTIONS.map((n) => (
                      <option key={n} value={n}>
                        {n} 条
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={useLlm}
                  onChange={(e) => setUseLlm(e.target.checked)}
                  className="rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                />
                LLM 汇总（失败自动回退）
              </label>

              {err && (
                <p className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {err}
                </p>
              )}
            </div>

            <div className="border-t border-slate-100 px-5 py-4">
              {busy ? (
                <button
                  type="button"
                  onClick={onCancel}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                >
                  <Square className="h-3.5 w-3.5 fill-current" />
                  取消搜集
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => void onRun()}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white shadow-sm hover:bg-emerald-500"
                >
                  <Sparkles className="h-4 w-4" />
                  开始搜集
                </button>
              )}
              <div className="mt-3 flex gap-3 text-sm">
                <Link to="/ai" className="text-slate-500 hover:text-slate-800">
                  ← AI 主页
                </Link>
                <Link
                  to="/ai/chat"
                  className="text-slate-500 hover:text-slate-800"
                >
                  SV 助手
                </Link>
              </div>
            </div>
          </>
        )}
      </aside>

      <main className="flex min-w-0 flex-1 flex-col bg-[#f0f3f8]">
        <div className="flex items-center justify-between border-b border-slate-200/80 bg-white/80 px-5 py-3 backdrop-blur sm:px-8">
          <button
            type="button"
            onClick={() => navigate("/ai")}
            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
          >
            <ArrowLeft className="h-4 w-4" />
            返回 AI 主页
          </button>
          <span
            className={`rounded-full px-3 py-1 text-sm font-medium ${
              busy
                ? "bg-amber-50 text-amber-700"
                : pack
                  ? "bg-emerald-50 text-emerald-700"
                  : "bg-slate-100 text-slate-500"
            }`}
          >
            {statusLabel}
          </span>
        </div>

        <div className="flex flex-1 flex-col overflow-y-auto px-5 py-6 sm:px-10 sm:py-8">
          {!pack && !busy && (
            <div className="flex flex-1 flex-col items-center justify-center text-center">
              <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-white text-emerald-600 shadow-sm ring-1 ring-slate-200/80">
                <Newspaper className="h-10 w-10" />
              </div>
              <h2 className="mt-6 text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
                准备生成证据包
              </h2>
              <p className="mt-3 max-w-lg text-base leading-relaxed text-slate-500">
                在左侧输入研究问题并开始搜集，会从资讯/研报/论文/帖子汇总概括。
              </p>
              <button
                type="button"
                onClick={() => void onRun()}
                className="mt-8 inline-flex items-center gap-2 rounded-full bg-slate-900 px-6 py-3 text-sm font-semibold text-white hover:bg-slate-800"
              >
                开始新搜集 →
              </button>
            </div>
          )}

          {busy && (
            <div className="flex flex-1 flex-col items-center justify-center gap-4 text-slate-500">
              <Loader2 className="h-9 w-9 animate-spin text-emerald-600" />
              <p className="text-base">正在检索在线资料并汇总…</p>
              <button
                type="button"
                onClick={onCancel}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                <Square className="h-3.5 w-3.5 fill-current" />
                取消
              </button>
            </div>
          )}

          {pack && !busy && (
            <div className="mx-auto w-full max-w-5xl space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-3 text-sm text-slate-500">
                  <span className="rounded-full bg-white px-3 py-1 font-mono text-xs ring-1 ring-slate-200">
                    {pack.pack_id}
                  </span>
                  <span>{modeLabel}</span>
                  <span>
                    {pack.stats?.returned ?? pack.items?.length ?? 0} 条 · 检索{" "}
                    {pack.stats?.retrieved ?? "—"}
                  </span>
                  <span>{pack.stats?.elapsed_ms ?? "—"} ms</span>
                </div>
                <button
                  type="button"
                  disabled={!pack.items?.length}
                  onClick={() => {
                    setActivePackForIdea(pack);
                    navigate(
                      `/ai/idea?pack=${encodeURIComponent(pack.pack_id)}`,
                    );
                  }}
                  className="inline-flex items-center gap-1.5 rounded-full bg-amber-500 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Lightbulb className="h-4 w-4" />
                  基于此生成研究假设 →
                </button>
              </div>

              {pack.digest && (
                <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-emerald-100/80 sm:p-6">
                  <h3 className="text-base font-semibold text-emerald-900">
                    资料汇总
                  </h3>
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-slate-800 sm:text-base">
                    {pack.digest}
                  </p>
                </section>
              )}

              {(pack.digest_bullets || []).length > 0 && (
                <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200/80 sm:p-6">
                  <h3 className="text-base font-semibold text-slate-800">要点</h3>
                  <ul className="mt-3 space-y-2">
                    {pack.digest_bullets.map((b, i) => (
                      <li
                        key={`${i}-${b.text.slice(0, 12)}`}
                        className="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700"
                      >
                        {b.text}
                        <div className="mt-1 font-mono text-xs text-slate-400">
                          {(b.item_ids || []).join(", ")}
                        </div>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {(pack.gaps || []).length > 0 && (
                <section className="rounded-2xl bg-amber-50 px-5 py-4 text-sm text-amber-900 ring-1 ring-amber-100">
                  <div className="font-semibold">缺口</div>
                  <ul className="mt-2 list-disc pl-5">
                    {pack.gaps.map((g) => (
                      <li key={g}>{g}</li>
                    ))}
                  </ul>
                </section>
              )}

              <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200/80 sm:p-6">
                <h3 className="text-base font-semibold text-slate-800">
                  资料条目
                </h3>
                <p className="mt-1 text-xs text-slate-400">
                  资讯可进站内详情；研报/论文/帖子打开原文链接
                </p>
                <ul className="mt-3 space-y-3">
                  {(pack.items || []).map((it) => {
                    const newsPath =
                      it.sv_news_id != null ? newsHref(it.sv_news_id) : null;
                    const extUrl =
                      !newsPath && it.url?.startsWith("http") ? it.url : null;
                    return (
                      <li
                        key={it.id}
                        className="rounded-xl border border-slate-100 bg-slate-50/60 px-4 py-3"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            {newsPath ? (
                              <Link
                                to={newsPath}
                                className="text-sm font-medium text-slate-900 hover:text-emerald-700 sm:text-base"
                              >
                                {it.title}
                              </Link>
                            ) : extUrl ? (
                              <a
                                href={extUrl}
                                target="_blank"
                                rel="noreferrer"
                                className="text-sm font-medium text-slate-900 hover:text-emerald-700 sm:text-base"
                              >
                                {it.title}
                              </a>
                            ) : (
                              <div className="text-sm font-medium text-slate-900 sm:text-base">
                                {it.title}
                              </div>
                            )}
                            <div className="mt-1 text-sm text-slate-500">
                              <span className="mr-1.5 rounded bg-white px-1.5 py-0.5 text-[11px] font-medium text-slate-600 ring-1 ring-slate-200">
                                {({
                                  news: "资讯",
                                  sv_news: "资讯",
                                  report: "研报",
                                  paper: "论文",
                                  post: "帖子",
                                } as Record<string, string>)[it.source_type] ||
                                  it.source_type}
                              </span>
                              {it.source_label || it.source_type}
                              {it.published_at
                                ? ` · ${String(it.published_at).slice(0, 16).replace("T", " ")}`
                                : ""}
                            </div>
                          </div>
                          {(newsPath || extUrl) && (
                            <ExternalLink className="mt-1 h-4 w-4 shrink-0 text-slate-400" />
                          )}
                        </div>
                        {it.snippet && (
                          <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-slate-600">
                            {it.snippet}
                          </p>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </section>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
