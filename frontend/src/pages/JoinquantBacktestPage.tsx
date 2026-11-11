import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Loader2,
  Play,
  RotateCcw,
  Upload,
  XCircle,
} from "lucide-react";
import { FactorCodeEditor } from "@/components/FactorCodeEditor";
import {
  cancelJoinquantRun,
  getJoinquantRun,
  precheckJoinquant,
  submitJoinquantRun,
  type JoinquantPrecheck,
  type JoinquantRunStatus,
} from "@/lib/joinquantStrategyApi";

const SAMPLE = `# 聚宽策略示例：每日目标权重
def initialize(context):
    g.security = '600519.XSHG'
    run_daily(rebalance, time='open')

def rebalance(context):
    order_target_percent(g.security, 0.2)
`;

const POLL_INTERVAL_MS = 3000;
const ACTIVE = new Set(["queued", "running"]);

const STATUS_TEXT: Record<string, string> = {
  queued: "排队中",
  running: "回测中",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

function fmtPct(value: unknown): string {
  const n = Number(value);
  return Number.isFinite(n) ? `${(n * 100).toFixed(2)}%` : "—";
}

/** RE 把指标放在 result.metrics（旧版也回显在 result 顶层），两处都兼容。 */
function resultMetric(
  run: JoinquantRunStatus | null,
  key: "total_return" | "max_drawdown",
): unknown {
  const result = (run?.result || {}) as Record<string, unknown>;
  const metrics = (result.metrics || {}) as Record<string, unknown>;
  return metrics[key] ?? result[key];
}

export function JoinquantBacktestPage() {
  const [code, setCode] = useState(SAMPLE);
  const [start, setStart] = useState("2024-01-01");
  const [end, setEnd] = useState("2024-06-30");
  const [benchmark, setBenchmark] = useState("CSI300");
  const [capital, setCapital] = useState("1000000");
  const [check, setCheck] = useState<JoinquantPrecheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [run, setRun] = useState<JoinquantRunStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const active = run ? ACTIVE.has(run.status) : false;
  // 业务错误可能挂在 result.error 上（RE 旧版语义：status=succeeded 但 result.error 非空）
  const runError = run ? run.error || run.result?.error || null : null;
  const runUnsupported = run ? run.unsupported_api || run.result?.unsupported_api || null : null;
  const runFailed = !!run && (run.status === "failed" || (run.status !== "cancelled" && !!runError));
  const blockers = useMemo(
    () => (check ? check.issues.filter((i) => i.severity === "blocker") : []),
    [check],
  );

  useEffect(() => {
    if (!run || !ACTIVE.has(run.status)) return;
    const timer = window.setTimeout(async () => {
      try {
        const next = await getJoinquantRun(run.run_id);
        setRun(next);
        if (!ACTIVE.has(next.status)) setBusy(false);
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : String(exc));
        setBusy(false);
      }
    }, POLL_INTERVAL_MS);
    return () => window.clearTimeout(timer);
  }, [run]);

  async function onPrecheck() {
    setError(null);
    setChecking(true);
    try {
      setCheck(await precheckJoinquant(code));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setChecking(false);
    }
  }

  async function onSubmit() {
    setError(null);
    setBusy(true);
    try {
      const created = await submitJoinquantRun({
        code,
        start,
        end,
        benchmark: benchmark || undefined,
        initial_capital: Number(capital) || undefined,
      });
      setRun({ run_id: created.run_id, status: created.status });
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
      setBusy(false);
    }
  }

  async function onCancel() {
    if (!run) return;
    try {
      setRun(await cancelJoinquantRun(run.run_id));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    }
  }

  async function onUpload(file: File | null) {
    if (!file) return;
    const text = await file.text();
    setCode(text);
    setCheck(null);
    setRun(null);
  }

  const canSubmit = !!check?.can_run_directly && !busy && !active;

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <Link
            to="/strategy/library"
            className="mb-1 inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> 返回策略库
          </Link>
          <h1 className="text-lg font-bold text-slate-900">聚宽策略直跑</h1>
          <p className="mt-1 text-xs text-slate-500">
            原始聚宽源码直接回测，不做转写；提交前会做能力预检，有阻断项不允许运行。
          </p>
        </div>
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
        >
          <Upload className="h-4 w-4" /> 上传 .py
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".py,.txt"
          className="hidden"
          onChange={(e) => void onUpload(e.target.files?.[0] || null)}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="rounded-xl border border-slate-200 bg-white p-3">
          <FactorCodeEditor value={code} onChange={(v) => { setCode(v); setCheck(null); }} height="420px" />
        </div>

        <div className="space-y-3">
          <div className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
            <div className="grid grid-cols-2 gap-2">
              <label className="text-xs text-slate-500">
                开始
                <input value={start} onChange={(e) => setStart(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5" />
              </label>
              <label className="text-xs text-slate-500">
                结束
                <input value={end} onChange={(e) => setEnd(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5" />
              </label>
              <label className="text-xs text-slate-500">
                基准（CSI300 / CSI500）
                <input value={benchmark} onChange={(e) => setBenchmark(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5" />
              </label>
              <label className="text-xs text-slate-500">
                初始资金
                <input value={capital} onChange={(e) => setCapital(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5" />
              </label>
            </div>

            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={() => void onPrecheck()}
                disabled={checking || busy}
                className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                {checking ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                预检
              </button>
              <button
                type="button"
                onClick={() => void onSubmit()}
                disabled={!canSubmit}
                className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
              >
                <Play className="h-4 w-4" /> 提交回测
              </button>
            </div>
            {!check ? (
              <p className="mt-2 text-xs text-slate-400">先点「预检」，通过后才能提交。</p>
            ) : check.can_run_directly ? (
              <p className="mt-2 text-xs text-emerald-600">预检通过，可直接回测（{check.engine || "event"}）。</p>
            ) : (
              <p className="mt-2 text-xs text-rose-600">存在 {check.blocker_count} 个阻断项，见下方。</p>
            )}
          </div>

          {error ? (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">{error}</div>
          ) : null}

          {check && check.issues.length ? (
            <div className="rounded-xl border border-slate-200 bg-white p-3">
              <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-slate-700">
                <AlertTriangle className="h-3.5 w-3.5" /> 预检问题（{check.issues.length}）
                {check.capabilities_version ? (
                  <span className="ml-auto font-normal text-slate-400">能力清单 {check.capabilities_version}</span>
                ) : null}
              </div>
              <ul className="space-y-2">
                {check.issues.map((issue, idx) => (
                  <li key={`${issue.code}-${idx}`} className="text-xs">
                    <div className="flex items-center gap-1.5">
                      {issue.severity === "blocker" ? (
                        <XCircle className="h-3.5 w-3.5 text-rose-500" />
                      ) : (
                        <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
                      )}
                      <span className="font-medium text-slate-800">{issue.title}</span>
                      {issue.line ? <span className="text-slate-400">L{issue.line}</span> : null}
                      <span className="ml-auto rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">{issue.code}</span>
                    </div>
                    {issue.why ? <p className="mt-0.5 pl-5 text-slate-500">{issue.why}</p> : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {run ? (
            <div className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
              <div className="flex items-center justify-between">
                <span className={`font-semibold ${runFailed ? "text-rose-600" : "text-slate-800"}`}>
                  {runFailed ? "失败" : STATUS_TEXT[run.status] || run.status}
                  {active ? <Loader2 className="ml-1 inline h-3.5 w-3.5 animate-spin text-slate-400" /> : null}
                </span>
                {active ? (
                  <button type="button" onClick={() => void onCancel()} className="text-xs text-slate-500 hover:text-rose-600">
                    取消
                  </button>
                ) : run.status === "failed" ? (
                  <button type="button" onClick={() => setRun(null)} className="inline-flex items-center gap-1 text-xs text-slate-500">
                    <RotateCcw className="h-3 w-3" /> 重来
                  </button>
                ) : null}
              </div>
              <p className="mt-1 break-all text-[11px] text-slate-400">run_id {run.run_id}</p>
              {runError ? (
                <p className="mt-2 break-words text-xs text-rose-600">
                  {runError}
                  {runUnsupported && runUnsupported !== runError ? (
                    <span className="ml-1 font-mono">({runUnsupported})</span>
                  ) : null}
                </p>
              ) : null}
              {run.result?.meta ? (
                <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-slate-600">
                  <dt className="text-slate-400">code_hash</dt>
                  <dd className="truncate font-mono">{run.result.meta.code_hash || "—"}</dd>
                  <dt className="text-slate-400">data_release</dt>
                  <dd className="truncate font-mono">{run.result.meta.data_release_id || "—"}</dd>
                  <dt className="text-slate-400">成交口径</dt>
                  <dd>{String((run.result.assumptions?.execution as string) || "—")}</dd>
                  <dt className="text-slate-400">价格来源</dt>
                  <dd>{String((run.result.assumptions?.price_source as string) || "—")}</dd>
                  <dt className="text-slate-400">总收益</dt>
                  <dd>{fmtPct(resultMetric(run, "total_return"))}</dd>
                  <dt className="text-slate-400">最大回撤</dt>
                  <dd>{fmtPct(resultMetric(run, "max_drawdown"))}</dd>
                </dl>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
