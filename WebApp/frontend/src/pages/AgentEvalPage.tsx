import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, BadgeCheck, History, Loader2 } from "lucide-react";
import { loadChainReport, runFactorEval, type EvalResult } from "@/lib/agentChain";
import {
  loadEvalHistory,
  loadLastEval,
  pushEvalHistory,
  saveLastEval,
  type EvalHistoryEntry,
} from "@/lib/cdeHistory";

export function AgentEvalPage() {
  const navigate = useNavigate();
  const report = useMemo(() => loadChainReport(), []);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [histTick, setHistTick] = useState(0);
  const history = useMemo(() => loadEvalHistory(), [histTick]);
  const [evalOut, setEvalOut] = useState<EvalResult | null>(() => loadLastEval());

  useEffect(() => {
    const saved = loadLastEval();
    if (!saved?.eval_id) return;
    if (loadEvalHistory().some((h) => h.eval_id === saved.eval_id)) return;
    pushEvalHistory({
      eval_id: saved.eval_id,
      report_id: report?.report_id || "",
      verdict: saved.verdict,
      note: saved.note,
      finishedAt: new Date().toISOString(),
      eval: saved,
    });
    setHistTick((n) => n + 1);
  }, [report]);

  async function onRun() {
    if (!report || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const out = await runFactorEval({ report });
      setEvalOut(out);
      saveLastEval(out);
      pushEvalHistory({
        eval_id: out.eval_id,
        report_id: report.report_id,
        verdict: out.verdict,
        note: out.note,
        finishedAt: new Date().toISOString(),
        eval: out,
      });
      setHistTick((n) => n + 1);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function restore(h: EvalHistoryEntry) {
    setErr(null);
    setEvalOut(h.eval);
    saveLastEval(h.eval);
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-[#f0f3f8] lg:flex-row">
      <aside className="flex w-full shrink-0 flex-col border-b bg-white lg:h-full lg:w-[22rem] lg:border-b-0 lg:border-r">
        <div className="flex items-center gap-3 border-b px-5 py-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700">
            <BadgeCheck className="h-5 w-5" />
          </div>
          <div>
            <div className="text-base font-semibold">评价入库 Agent</div>
            <div className="text-sm text-slate-500">雏形 · 不自动写入库</div>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4 text-sm text-slate-600">
          {report ? `已载入报告 ${report.report_id}` : "请先跑回测报告，或从下方历史回看。"}
          {history.length > 0 && (
            <div className="mt-5">
              <div className="flex items-center gap-1.5 text-sm font-medium text-slate-700">
                <History className="h-3.5 w-3.5" />
                本机评价历史
              </div>
              <ul className="mt-2 space-y-2">
                {history.slice(0, 8).map((h) => (
                  <li key={h.eval_id}>
                    <button
                      type="button"
                      onClick={() => restore(h)}
                      className={`w-full rounded-xl border px-3 py-2 text-left text-sm hover:border-emerald-200 hover:bg-emerald-50/40 ${
                        evalOut?.eval_id === h.eval_id
                          ? "border-emerald-300 bg-emerald-50/50"
                          : "border-slate-100 bg-slate-50"
                      }`}
                    >
                      <div className="font-medium text-slate-800">
                        {h.verdict === "review" ? "建议复核" : "不建议入库"}
                      </div>
                      <div className="mt-0.5 line-clamp-2 text-xs text-slate-400">{h.note}</div>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div className="border-t px-5 py-4">
          <button
            type="button"
            disabled={!report || busy}
            onClick={() => void onRun()}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-50"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            给出入库建议
          </button>
          <Link to="/ai" className="mt-3 inline-block text-sm text-slate-500">
            ← AI 主页
          </Link>
        </div>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center border-b bg-white/80 px-5 py-3">
          <button type="button" onClick={() => navigate("/ai")} className="inline-flex items-center gap-1.5 text-sm">
            <ArrowLeft className="h-4 w-4" />
            返回 AI 主页
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-6">
          {err && <div className="mb-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-800">{err}</div>}
          {evalOut && (
            <div className="mx-auto max-w-3xl rounded-2xl bg-white p-6 ring-1 ring-slate-200">
              <div className="text-lg font-semibold">
                {evalOut.verdict === "review" ? "建议人工复核，暂不自动入库" : "不建议入库"}
              </div>
              <p className="mt-2 text-sm text-slate-700">{evalOut.note}</p>
              <ul className="mt-3 list-disc pl-5 text-sm text-slate-600">
                {evalOut.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              {(evalOut.warnings || []).length > 0 && (
                <p className="mt-4 text-xs text-slate-400">{evalOut.warnings!.join(" · ")}</p>
              )}
            </div>
          )}
          {!evalOut && !busy && (
            <p className="text-center text-slate-500">评价只给建议，不会改因子库。</p>
          )}
        </div>
      </main>
    </div>
  );
}
