import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, History, LineChart, Loader2 } from "lucide-react";
import {
  loadChainDraft,
  loadChainReport,
  runFactorBacktest,
  saveChainReport,
  type BacktestReport,
} from "@/lib/agentChain";
import {
  loadBacktestHistory,
  pushBacktestHistory,
  type BacktestHistoryEntry,
} from "@/lib/cdeHistory";

const METRIC_LABELS: { key: string; label: string; kind: "pct" | "num" }[] = [
  { key: "annual_return", label: "年化", kind: "pct" },
  { key: "sharpe", label: "夏普", kind: "num" },
  { key: "sortino", label: "索提诺", kind: "num" },
  { key: "calmar", label: "卡玛", kind: "num" },
  { key: "max_drawdown", label: "最大回撤", kind: "pct" },
  { key: "volatility", label: "波动", kind: "pct" },
  { key: "ic", label: "IC", kind: "num" },
  { key: "rank_ic", label: "Rank IC", kind: "num" },
  { key: "win_rate", label: "胜率", kind: "pct" },
  { key: "turnover", label: "换手", kind: "num" },
];

function fmt(v: unknown, kind: "pct" | "num") {
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return "—";
  if (kind === "pct") return `${(n * 100).toFixed(2)}%`;
  return n.toFixed(4);
}

export function AgentBacktestPage() {
  const navigate = useNavigate();
  const draft = useMemo(() => loadChainDraft(), []);
  const hint = draft?.backtest_hint;
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [histTick, setHistTick] = useState(0);
  const history = useMemo(() => loadBacktestHistory(), [histTick]);
  const [report, setReport] = useState<BacktestReport | null>(() => loadChainReport());
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const saved = loadChainReport();
    if (!saved?.report_id) return;
    if (loadBacktestHistory().some((h) => h.report_id === saved.report_id)) return;
    const name = String(saved.request?.factor_name || draft?.factor.factor_name || saved.report_id);
    const start = String(saved.request?.start || draft?.backtest_hint.start || "");
    const end = String(saved.request?.end || draft?.backtest_hint.end || "");
    pushBacktestHistory({
      report_id: saved.report_id,
      factor_name: name,
      window: start && end ? `${start} ~ ${end}` : name,
      finishedAt: new Date().toISOString(),
      report: saved,
    });
    setHistTick((n) => n + 1);
  }, [draft]);

  async function onRun() {
    if (!hint || busy) return;
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setBusy(true);
    setErr(null);
    try {
      const out = await runFactorBacktest(
        { backtest_hint: hint, factor: draft?.factor, draft_id: draft?.draft_id },
        ac.signal,
      );
      setReport(out);
      saveChainReport(out);
      pushBacktestHistory({
        report_id: out.report_id,
        factor_name: hint.factor_name,
        window: `${hint.start} ~ ${hint.end}`,
        finishedAt: new Date().toISOString(),
        report: out,
      });
      setHistTick((n) => n + 1);
    } catch (e) {
      if ((e as Error)?.name === "AbortError") return;
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function restore(h: BacktestHistoryEntry) {
    setErr(null);
    setReport(h.report);
    saveChainReport(h.report);
  }

  const metrics = report?.metrics || {};

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-[#f0f3f8] lg:flex-row">
      <aside className="flex w-full shrink-0 flex-col border-b border-slate-200 bg-white lg:h-full lg:w-[22rem] lg:border-b-0 lg:border-r">
        <div className="flex items-center gap-3 border-b px-5 py-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-sky-50 text-sky-700">
            <LineChart className="h-5 w-5" />
          </div>
          <div>
            <div className="text-base font-semibold">回测报告 Agent</div>
            <div className="text-sm text-slate-500">雏形 · 调用平台回测</div>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4 text-sm text-slate-600">
          {hint ? (
            <ul className="space-y-1 font-mono text-xs">
              <li>{hint.factor_name}</li>
              <li>
                {hint.start} ~ {hint.end}
              </li>
              <li>{hint.universe}</li>
              {hint.oos_split ? <li>样本外 {hint.oos_split}</li> : null}
            </ul>
          ) : (
            <p>请先生成因子草稿，或从下方历史回看。</p>
          )}
          {history.length > 0 && (
            <div className="mt-5">
              <div className="flex items-center gap-1.5 text-sm font-medium text-slate-700">
                <History className="h-3.5 w-3.5" />
                本机回测历史
              </div>
              <ul className="mt-2 space-y-2">
                {history.slice(0, 8).map((h) => (
                  <li key={h.report_id}>
                    <button
                      type="button"
                      onClick={() => restore(h)}
                      className={`w-full rounded-xl border px-3 py-2 text-left text-sm hover:border-sky-200 hover:bg-sky-50/40 ${
                        report?.report_id === h.report_id
                          ? "border-sky-300 bg-sky-50/50"
                          : "border-slate-100 bg-slate-50"
                      }`}
                    >
                      <div className="font-mono text-xs text-slate-800">{h.factor_name}</div>
                      <div className="mt-0.5 text-xs text-slate-400">{h.window}</div>
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
            disabled={!hint || busy}
            onClick={() => void onRun()}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-sky-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-50"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {busy ? "回测中（可能较久）…" : "发送回测"}
          </button>
          <Link to="/ai" className="mt-3 inline-block text-sm text-slate-500">
            ← AI 主页
          </Link>
        </div>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b bg-white/80 px-5 py-3">
          <button type="button" onClick={() => navigate("/ai")} className="inline-flex items-center gap-1.5 text-sm">
            <ArrowLeft className="h-4 w-4" />
            返回 AI 主页
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-6">
          {err && <div className="mb-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-800">{err}</div>}
          {report && (
            <div className="mx-auto max-w-5xl space-y-4">
              {report.error && (
                <div className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900">{String(report.error)}</div>
              )}
              <section className="rounded-2xl bg-white p-5 ring-1 ring-slate-200">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className="font-semibold">指标摘要</h3>
                  <span className="text-xs text-slate-400">{report.report_id}</span>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
                  {METRIC_LABELS.map((m) => (
                    <div key={m.key} className="rounded-xl bg-slate-50 px-3 py-2">
                      <div className="text-xs text-slate-500">{m.label}</div>
                      <div className="mt-0.5 font-mono text-sm text-slate-800">
                        {fmt(metrics[m.key], m.kind)}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
              {(report.warnings || []).length > 0 && (
                <p className="text-xs text-slate-400">{report.warnings!.join(" · ")}</p>
              )}
              <Link
                to="/ai/factor-eval"
                className="inline-flex rounded-full bg-sky-600 px-4 py-2 text-sm font-semibold text-white"
              >
                送给评价 Agent →
              </Link>
            </div>
          )}
          {!report && !busy && (
            <p className="text-center text-slate-500">确认区间后发送。换区间结果可能差很多。</p>
          )}
        </div>
      </main>
    </div>
  );
}
