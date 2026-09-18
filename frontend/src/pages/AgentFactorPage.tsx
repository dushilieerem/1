import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, FlaskConical, History, Loader2, Sparkles } from "lucide-react";
import {
  loadChainDraft,
  loadChainIdea,
  runFactorDraft,
  saveChainDraft,
  saveChainIdea,
  type FactorDraftBundle,
} from "@/lib/agentChain";
import {
  loadFactorHistory,
  pushFactorHistory,
  type FactorHistoryEntry,
} from "@/lib/cdeHistory";

export function AgentFactorPage() {
  const navigate = useNavigate();
  const chain = useMemo(() => loadChainIdea(), []);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [histTick, setHistTick] = useState(0);
  const history = useMemo(() => loadFactorHistory(), [histTick]);
  const [draft, setDraft] = useState<FactorDraftBundle | null>(() => {
    const saved = loadChainDraft();
    if (!saved) return null;
    const ideaId = chain?.idea?.id;
    if (!ideaId) return saved;
    return saved.idea_id === ideaId ? saved : null;
  });
  const [idea, setIdea] = useState(chain?.idea);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const saved = loadChainDraft();
    if (!saved?.draft_id) return;
    if (loadFactorHistory().some((h) => h.draft_id === saved.draft_id)) return;
    const title = chain?.idea?.title || saved.factor.factor_name;
    if (!chain?.idea) return;
    pushFactorHistory({
      draft_id: saved.draft_id,
      title,
      factor_name: saved.factor.factor_name,
      finishedAt: new Date().toISOString(),
      idea: chain.idea,
      pack_id: chain.pack_id,
      bundle_id: chain.bundle_id,
      draft: saved,
    });
    setHistTick((n) => n + 1);
  }, [chain]);
  const hint = draft?.backtest_hint;
  const factor = draft?.factor;

  async function onGenerate() {
    if (!idea || busy) return;
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setBusy(true);
    setErr(null);
    try {
      const out = await runFactorDraft(
        {
          idea,
          pack_id: chain?.pack_id,
          bundle_id: chain?.bundle_id,
        },
        ac.signal,
      );
      setDraft(out);
      saveChainDraft(out);
      pushFactorHistory({
        draft_id: out.draft_id,
        title: idea.title,
        factor_name: out.factor.factor_name,
        finishedAt: new Date().toISOString(),
        idea,
        pack_id: chain?.pack_id,
        bundle_id: chain?.bundle_id,
        draft: out,
      });
      setHistTick((n) => n + 1);
    } catch (e) {
      if ((e as Error)?.name === "AbortError") return;
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function restore(h: FactorHistoryEntry) {
    setErr(null);
    setIdea(h.idea);
    setDraft(h.draft);
    saveChainDraft(h.draft);
    saveChainIdea(h.idea, { pack_id: h.pack_id, bundle_id: h.bundle_id });
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-[#f0f3f8] lg:flex-row">
      <aside className="flex w-full shrink-0 flex-col border-b border-slate-200 bg-white lg:h-full lg:w-[22rem] lg:border-b-0 lg:border-r">
        <div className="flex items-center gap-3 border-b border-slate-100 px-5 py-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-50 text-violet-700">
            <FlaskConical className="h-5 w-5" />
          </div>
          <div>
            <div className="text-base font-semibold">因子草稿 Agent</div>
            <div className="text-sm text-slate-500">假设 → 平台可回测代码</div>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4 text-sm">
          {idea ? (
            <>
              <div className="font-medium text-slate-800">{idea.title}</div>
              <p className="mt-2 leading-relaxed text-slate-600">{idea.thesis}</p>
              {idea.validity && (
                <div className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
                  <div className="font-medium text-slate-700">
                    时段建议（可不采用）
                  </div>
                  {(idea.validity.suggested_start || idea.validity.suggested_end) && (
                    <div className="mt-1 font-mono">
                      {idea.validity.suggested_start || "?"} ~{" "}
                      {idea.validity.suggested_end || "?"}
                      {idea.validity.oos_split
                        ? ` · 样本外参考 ${idea.validity.oos_split}`
                        : ""}
                    </div>
                  )}
                  {idea.validity.why_window && (
                    <div className="mt-1">{idea.validity.why_window}</div>
                  )}
                </div>
              )}
              {idea.factor_prompt && (
                <pre className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap rounded-xl bg-slate-900 px-3 py-2 text-xs leading-relaxed text-slate-100">
                  {idea.factor_prompt}
                </pre>
              )}
            </>
          ) : (
            <p className="text-slate-500">
              请先在研究假设页点「转成因子草稿」。也可从下方历史回看。
            </p>
          )}
          {history.length > 0 && (
            <div className="mt-5">
              <div className="flex items-center gap-1.5 text-sm font-medium text-slate-700">
                <History className="h-3.5 w-3.5" />
                本机草稿历史
              </div>
              <ul className="mt-2 space-y-2">
                {history.slice(0, 8).map((h) => (
                  <li key={h.draft_id}>
                    <button
                      type="button"
                      onClick={() => restore(h)}
                      className={`w-full rounded-xl border px-3 py-2 text-left text-sm hover:border-violet-200 hover:bg-violet-50/40 ${
                        draft?.draft_id === h.draft_id
                          ? "border-violet-300 bg-violet-50/50"
                          : "border-slate-100 bg-slate-50"
                      }`}
                    >
                      <div className="line-clamp-2 font-medium text-slate-800">{h.title}</div>
                      <div className="mt-0.5 font-mono text-xs text-slate-400">
                        {h.factor_name}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div className="border-t border-slate-100 px-5 py-4">
          <button
            type="button"
            disabled={!idea || busy}
            onClick={() => void onGenerate()}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-3 text-sm font-semibold text-white hover:bg-violet-500 disabled:opacity-50"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            {busy ? "生成中…" : "生成因子代码"}
          </button>
          <div className="mt-3 flex flex-wrap gap-3 text-sm">
            <Link to="/ai" className="text-slate-500 hover:text-slate-800">
              ← AI 主页
            </Link>
            <Link to="/ai/idea" className="text-slate-500 hover:text-slate-800">
              研究假设
            </Link>
          </div>
        </div>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b bg-white/80 px-5 py-3">
          <button
            type="button"
            onClick={() => navigate("/ai")}
            className="inline-flex items-center gap-1.5 text-sm text-slate-600"
          >
            <ArrowLeft className="h-4 w-4" />
            返回 AI 主页
          </button>
          <span className="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-500">
            {busy ? "Running" : draft ? "Ready" : "Idle"}
          </span>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-6 sm:px-8">
          {err && (
            <div className="mb-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-800">{err}</div>
          )}
          {!draft && !busy && (
            <p className="text-center text-slate-500">确认左侧假设后生成代码（人审后再回测）</p>
          )}
          {draft && factor && hint && (
            <div className="mx-auto max-w-5xl space-y-4">
              <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 sm:p-6">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div className="font-mono text-base text-violet-800">{factor.factor_name}</div>
                  <div className="text-xs text-slate-400">{draft.draft_id}</div>
                </div>
                {factor.formula_nl && (
                  <div className="mt-4">
                    <div className="text-xs font-medium text-slate-500">公式</div>
                    <p className="mt-1 text-sm text-slate-800">{factor.formula_nl}</p>
                  </div>
                )}
                {factor.description && (
                  <div className="mt-4">
                    <div className="text-xs font-medium text-slate-500">说明</div>
                    <p className="mt-1 text-sm leading-relaxed text-slate-700">{factor.description}</p>
                  </div>
                )}
                {(factor.used_fields || []).length > 0 && (
                  <div className="mt-4">
                    <div className="text-xs font-medium text-slate-500">使用字段</div>
                    <p className="mt-1 font-mono text-sm text-slate-700">
                      {factor.used_fields.join(" · ")}
                    </p>
                  </div>
                )}
                <div className="mt-4">
                  <div className="text-xs font-medium text-slate-500">代码</div>
                  <pre className="mt-1 overflow-auto rounded-xl bg-slate-900 p-4 text-xs text-slate-100">
                    {factor.factor_code}
                  </pre>
                </div>
                <div className="mt-4 grid gap-2 text-sm text-slate-600 sm:grid-cols-2">
                  <div>股票池 {hint.universe}</div>
                  <div>
                    回测窗 {hint.start} ~ {hint.end}
                  </div>
                  <div>样本外自 {hint.oos_split || "—"}</div>
                  <div>
                    {hint.groups} 组 · 调仓 {hint.rebalance_days} 日 · {hint.portfolio_type}
                  </div>
                </div>
                {(factor.assumptions || []).length > 0 && (
                  <ul className="mt-4 list-disc pl-5 text-xs text-slate-500">
                    {factor.assumptions!.map((a) => (
                      <li key={a}>{a}</li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="flex flex-wrap gap-3">
                <Link
                  to="/factor/detect"
                  className="rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white"
                >
                  去检测页
                </Link>
                <Link
                  to="/ai/factor-backtest"
                  className="rounded-full bg-violet-600 px-4 py-2 text-sm font-semibold text-white"
                >
                  发给回测 Agent →
                </Link>
              </div>
              {(draft.warnings || factor.warnings || []).length > 0 && (
                <p className="text-xs text-slate-400">
                  {[...(draft.warnings || []), ...(factor.warnings || [])].join(" · ")}
                </p>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
