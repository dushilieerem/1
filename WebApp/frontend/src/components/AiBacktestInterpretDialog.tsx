import { useState, type ReactNode } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Copy,
  FlaskConical,
  Info,
  Sparkles,
  X,
} from "lucide-react";
import {
  formatCoverageLabel,
  formatEvidenceWarning,
  formatExperimentClipboard,
  formatModeLabel,
  newInterpretIdempotencyKey,
  ygInterpretBacktest,
  type BacktestInterpretEvidenceItem,
  type BacktestInterpretExperiment,
  type BacktestInterpretFocus,
  type BacktestInterpretFinding,
  type BacktestInterpretRunContext,
  type BacktestInterpretType,
  type BacktestInterpretationResult,
} from "@/lib/aiBacktestInterpretApi";

type Props = {
  /** modal 时控制显隐；panel 时由父级条件渲染即可 */
  open?: boolean;
  onClose?: () => void;
  /** panel = 报告页左侧栏内嵌；modal = 弹窗（兼容旧用法） */
  variant?: "modal" | "panel";
  backtestType: BacktestInterpretType;
  result: Record<string, unknown> | null | undefined;
  runContext?: BacktestInterpretRunContext;
};

const FOCUS_OPTS: { value: BacktestInterpretFocus; label: string }[] = [
  { value: "overall", label: "综合" },
  { value: "risk", label: "风险" },
  { value: "robustness", label: "稳健性" },
  { value: "factor", label: "因子质量" },
  { value: "execution", label: "执行与换手" },
];

const EVIDENCE_LABELS: Record<string, string> = {
  "coverage.equity_points": "净值点数",
  "performance.total_return": "区间收益",
  "performance.annual_return": "年化收益",
  "performance.benchmark_return": "基准收益",
  "risk.max_drawdown": "最大回撤",
  "risk.sharpe": "夏普",
  "execution.turnover": "换手",
  "factor.ic_mean": "平均 IC",
  "assumption.validation_scheme": "验证方案",
  "assumption.commission_rate": "佣金",
  "assumption.stamp_tax": "印花税",
  "assumption.slippage_rate": "滑点",
};

function severityStyle(sev?: string) {
  const s = (sev || "").toLowerCase();
  if (s === "critical") {
    return "bg-red-50 text-red-700 ring-red-100";
  }
  if (s === "high" || s === "warning") {
    return "bg-amber-50 text-amber-800 ring-amber-100";
  }
  return "bg-slate-100 text-slate-600 ring-slate-200";
}

function severityLabel(sev?: string) {
  const s = (sev || "").toLowerCase();
  if (s === "critical") return "严重";
  if (s === "high") return "偏高";
  if (s === "warning") return "注意";
  if (s === "info") return "提示";
  return sev || "提示";
}

function confidenceLabel(c?: string) {
  if (!c) return null;
  const s = c.toLowerCase();
  if (s === "high") return "置信：高";
  if (s === "medium") return "置信：中";
  if (s === "low") return "置信：低";
  return `置信：${c}`;
}

function fmtEvidenceValue(
  value: unknown,
  unit?: string | null,
  status?: string,
): string {
  if (status === "unknown") return "未知";
  if (value == null) return status === "not_applicable" ? "不适用" : "—";
  if (typeof value === "number" && Number.isFinite(value)) {
    if (unit === "ratio") {
      return `${(value * 100).toFixed(2)}%`;
    }
    if (Math.abs(value) >= 100 || Number.isInteger(value)) {
      return String(value);
    }
    return value.toFixed(4);
  }
  return String(value);
}

function asRatioNumber(value: unknown, unit?: string | null): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return unit === "ratio" ? value : value;
}

function metricValueClass(evidenceId: string, value: unknown, unit?: string | null) {
  const n = asRatioNumber(value, unit);
  if (n == null) return "text-slate-900";
  if (evidenceId === "risk.max_drawdown") {
    return n < -0.2
      ? "text-red-700"
      : n < -0.1
        ? "text-amber-700"
        : "text-slate-900";
  }
  if (
    evidenceId === "performance.total_return" ||
    evidenceId === "performance.annual_return"
  ) {
    return n > 0 ? "text-emerald-700" : n < 0 ? "text-red-700" : "text-slate-900";
  }
  return "text-slate-900";
}

function relativeToBenchmark(
  totalReturn: unknown,
  totalUnit: string | null | undefined,
  benchReturn: unknown,
  benchUnit: string | null | undefined,
): string | null {
  const a = asRatioNumber(totalReturn, totalUnit);
  const b = asRatioNumber(benchReturn, benchUnit);
  if (a == null || b == null) return null;
  const diff = (a - b) * 100;
  const sign = diff > 0 ? "+" : "";
  return `相对基准 ${sign}${diff.toFixed(2)}%`;
}

function evidenceLabel(id: string) {
  return EVIDENCE_LABELS[id] || id;
}

export function AiBacktestInterpretDialog({
  open = true,
  onClose,
  variant = "modal",
  backtestType,
  result,
  runContext,
}: Props) {
  const isPanel = variant === "panel";
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [data, setData] = useState<BacktestInterpretationResult | null>(null);
  const [focus, setFocus] = useState<BacktestInterpretFocus>("overall");
  const [appliedFocus, setAppliedFocus] =
    useState<BacktestInterpretFocus | null>(null);
  const [expandedFinding, setExpandedFinding] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const run = async () => {
    if (!result || typeof result !== "object") {
      setErr("当前报告没有可用回测结果");
      return;
    }
    if (result.error != null && result.error !== "") {
      setErr("回测结果带错误，请先修复后再解读");
      return;
    }
    // 规则降级时关注方向/重复解读不会改结果，避免“点了没反应”
    if (
      data?.status === "ready" &&
      data.mode === "deterministic_fallback" &&
      appliedFocus === focus
    ) {
      setHint("当前为规则诊断，重复解读结果相同；关注方向仅在接上 AI 后才会重排建议。");
      return;
    }
    setBusy(true);
    setErr(null);
    setHint(null);
    setExpandedFinding(null);
    try {
      const out = await ygInterpretBacktest({
        backtest_type: backtestType,
        result,
        run_context: runContext,
        focus,
        question: null,
        idempotency_key: newInterpretIdempotencyKey(),
      });
      setData(out);
      setAppliedFocus(focus);
      if (
        out.status === "ready" &&
        out.mode === "deterministic_fallback" &&
        data
      ) {
        setHint("当前为规则诊断，换关注方向不会改变证据与诊断内容。");
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const handleClose = () => {
    setData(null);
    setErr(null);
    setHint(null);
    setFocus("overall");
    setAppliedFocus(null);
    setExpandedFinding(null);
    setCopiedId(null);
    onClose?.();
  };

  const interp = data?.interpretation;
  const findings = interp?.findings || [];
  const experiments = [...(interp?.experiments || [])].sort(
    (a, b) => (a.priority ?? 99) - (b.priority ?? 99),
  );
  const allEvidence = data?.evidence?.items || [];
  const evidenceById = new Map<string, BacktestInterpretEvidenceItem>();
  for (const it of allEvidence) {
    evidenceById.set(it.evidence_id, it);
  }

  const evidenceItems = allEvidence.filter((it) =>
    Boolean(EVIDENCE_LABELS[it.evidence_id]),
  );
  const bench = evidenceById.get("performance.benchmark_return");
  const warnings = data?.evidence?.warnings || [];
  const coverageLabel = formatCoverageLabel(data?.evidence?.coverage);
  const modeInfo = formatModeLabel(data?.mode);

  const copyExperiment = async (
    ex: BacktestInterpretExperiment,
    index: number,
  ) => {
    const textClip = formatExperimentClipboard(ex, index);
    const id = ex.experiment_id || String(index);
    try {
      await navigator.clipboard.writeText(textClip);
      setCopiedId(id);
      window.setTimeout(() => setCopiedId((cur) => (cur === id ? null : cur)), 1500);
    } catch {
      setErr("复制失败，请手动选中文案");
    }
  };

  const toggleFinding = (key: string) => {
    setExpandedFinding((cur) => (cur === key ? null : key));
  };

  const renderEvidenceRefs = (refs?: string[]) => {
    const ids = refs || [];
    if (!ids.length) {
      return (
        <p className="text-xs text-slate-400">本条未附带证据引用</p>
      );
    }
    return (
      <ul className="space-y-1.5">
        {ids.map((id) => {
          const it = evidenceById.get(id);
          return (
            <li
              key={id}
              className="flex flex-wrap items-baseline justify-between gap-2 rounded-lg bg-white/80 px-2.5 py-1.5 text-xs ring-1 ring-slate-100"
            >
              <span className="text-slate-500">{evidenceLabel(id)}</span>
              <span className="font-medium tabular-nums text-slate-800">
                {it
                  ? fmtEvidenceValue(it.value, it.unit, it.status)
                  : "（证据缺失）"}
              </span>
              {it?.status && it.status !== "observed" && it.status !== "derived" ? (
                <span className="w-full text-[10px] text-slate-400">
                  状态：{it.status}
                </span>
              ) : null}
              {(it?.limitations || []).length ? (
                <span className="w-full text-[10px] text-slate-400">
                  限制：{(it?.limitations || []).join("；")}
                </span>
              ) : null}
            </li>
          );
        })}
      </ul>
    );
  };

  if (!isPanel && !open) return null;

  const body = (
    <>
      <div className="relative border-b border-slate-100 px-5 py-4">
        <div className="pointer-events-none absolute inset-0 rounded-t-2xl bg-gradient-to-br from-violet-50 via-white to-cyan-50/40" />
        <div className="relative flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-2">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-violet-600 text-white shadow-sm shadow-violet-600/25">
              <Sparkles className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <h2 className="text-base font-bold leading-snug text-slate-900">
                AI 回测解读
              </h2>
              <p className="mt-0.5 text-xs leading-relaxed text-slate-500">
                基于本次{backtestType === "strategy" ? "策略" : "因子"}
                回测快照 · 仅供研究参考
              </p>
            </div>
          </div>
          {!isPanel && onClose ? (
            <button
              type="button"
              onClick={handleClose}
              className="relative shrink-0 rounded-lg p-1.5 text-slate-400 hover:bg-white/80 hover:text-slate-700"
            >
              <X className="h-4 w-4" />
            </button>
          ) : null}
        </div>
      </div>

      <div className="space-y-4 px-5 py-4">
        <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-3">
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-[140px] flex-1 text-xs text-slate-500">
              关注方向
              <select
                value={focus}
                onChange={(e) => {
                  setFocus(e.target.value as BacktestInterpretFocus);
                  setHint(null);
                }}
                className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-sm text-slate-800"
              >
                {FOCUS_OPTS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              disabled={busy}
              onClick={() => void run()}
              className="rounded-xl bg-violet-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-violet-700 disabled:opacity-50"
            >
              {busy ? "解读中…" : data ? "重新解读" : "开始解读"}
            </button>
          </div>
          {hint ? (
            <p className="mt-2 text-xs leading-relaxed text-amber-800">{hint}</p>
          ) : null}
        </div>

        {err ? (
          <div className="flex gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-3 text-sm text-red-700">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{err}</span>
          </div>
        ) : null}

        {busy && !data ? (
          <div className="flex flex-col items-center justify-center gap-2 py-12 text-sm text-slate-400">
            <Sparkles className="h-6 w-6 animate-pulse text-violet-400" />
            正在根据回测快照生成解读…
          </div>
        ) : null}

        {!busy && !data && !err ? (
          <div className="rounded-xl border border-dashed border-slate-200 px-4 py-10 text-center text-sm text-slate-400">
            点击「开始解读」
          </div>
        ) : null}

        {data ? (
          <div className="space-y-4">
            {data.status === "insufficient" ? (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-4">
                <div className="flex items-start gap-3">
                  <Info className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
                  <div>
                    <p className="font-semibold text-amber-950">
                      数据不足，暂无法完整解读
                    </p>
                    <p className="mt-1 text-sm leading-relaxed text-amber-900/90">
                      {interp?.summary ||
                        "有效净值点少于 60，建议拉长回测区间后再试。"}
                    </p>
                    <p className="mt-2 text-xs text-amber-800/80">
                      下一步：回到回测页拉长起止日期或换更长样本，重新跑通后再点解读。不展示实验建议。
                    </p>
                  </div>
                </div>
              </div>
            ) : null}

            {data.status === "rejected" ? (
              <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-4 text-sm text-red-800">
                <p className="font-semibold">回测结果被拒绝解读</p>
                <p className="mt-1">
                  原始回测带有业务错误。请先修复并重新执行回测，成功后再打开本解读。
                </p>
              </div>
            ) : null}

            {data.status === "ready" ? (
              <>
                <div className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                      解读摘要
                    </div>
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                      {modeInfo.short}
                    </span>
                  </div>
                  <p className="text-[15px] leading-relaxed text-slate-800">
                    {interp?.summary || "暂无摘要"}
                  </p>
                </div>

                {warnings.length || coverageLabel ? (
                  <div className="rounded-xl border border-amber-100 bg-amber-50/70 px-3.5 py-3">
                    <p className="mb-1.5 text-xs font-semibold text-amber-900">
                      证据提示
                      {coverageLabel ? (
                        <span className="ml-2 font-normal text-amber-700/80">
                          {coverageLabel}
                        </span>
                      ) : null}
                    </p>
                    {warnings.length ? (
                      <ul className="space-y-1">
                        {warnings.map((w) => (
                          <li
                            key={w}
                            className="flex gap-2 text-sm leading-relaxed text-amber-950/90"
                          >
                            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
                            <span>{formatEvidenceWarning(w)}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-sm text-amber-900/80">
                        无额外告警码；覆盖状态见上。
                      </p>
                    )}
                  </div>
                ) : null}

                {evidenceItems.length ? (
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
                    {evidenceItems.map((it) => {
                      const rel =
                        it.evidence_id === "performance.total_return" && bench
                          ? relativeToBenchmark(
                              it.value,
                              it.unit,
                              bench.value,
                              bench.unit,
                            )
                          : null;
                      return (
                        <div
                          key={it.evidence_id}
                          className="rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-2.5"
                        >
                          <p className="text-[11px] text-slate-400">
                            {evidenceLabel(it.evidence_id)}
                          </p>
                          <p
                            className={`mt-0.5 text-sm font-semibold tabular-nums ${metricValueClass(it.evidence_id, it.value, it.unit)}`}
                          >
                            {fmtEvidenceValue(it.value, it.unit, it.status)}
                          </p>
                          {rel ? (
                            <p className="mt-0.5 text-[10px] text-slate-400">
                              {rel}
                            </p>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                ) : null}

                {findings.length ? (
                  <div>
                    <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                      诊断发现
                      <span className="ml-2 font-normal normal-case tracking-normal text-slate-400">
                        点击条目可核对证据
                      </span>
                    </h3>
                    <ul className="space-y-2">
                      {findings.map((f, i) => (
                        <FindingRow
                          key={f.finding_id || String(i)}
                          finding={f}
                          index={i}
                          expanded={
                            expandedFinding === (f.finding_id || String(i))
                          }
                          onToggle={() =>
                            toggleFinding(f.finding_id || String(i))
                          }
                          renderEvidenceRefs={renderEvidenceRefs}
                        />
                      ))}
                    </ul>
                  </div>
                ) : null}

                {experiments.length ? (
                  <div>
                    <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400">
                      <FlaskConical className="h-3.5 w-3.5" />
                      下一轮实验建议
                    </h3>
                    <ol className="space-y-2">
                      {experiments.map((ex, i) => {
                        const id = ex.experiment_id || String(i);
                        return (
                          <li
                            key={id}
                            className="rounded-xl border border-violet-100 bg-gradient-to-br from-violet-50/80 to-white px-3.5 py-3"
                          >
                            <div className="flex items-start gap-2.5">
                              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-violet-600 text-[11px] font-bold text-white">
                                {ex.priority ?? i + 1}
                              </span>
                              <div className="min-w-0 flex-1">
                                <div className="flex items-start justify-between gap-2">
                                  <p className="font-semibold text-slate-900">
                                    {ex.hypothesis || ex.experiment_id}
                                  </p>
                                  <button
                                    type="button"
                                    onClick={() => void copyExperiment(ex, i)}
                                    className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-violet-100 bg-white px-2 py-1 text-[11px] text-violet-700 hover:bg-violet-50"
                                  >
                                    <Copy className="h-3 w-3" />
                                    {copiedId === id ? "已复制" : "复制"}
                                  </button>
                                </div>
                                {ex.primary_variable ? (
                                  <p className="mt-0.5 text-xs text-slate-500">
                                    主变量：{ex.primary_variable}
                                  </p>
                                ) : null}
                                {ex.validation_method ? (
                                  <p className="mt-1.5 text-sm text-slate-600">
                                    {ex.validation_method}
                                  </p>
                                ) : null}
                                {(ex.expected_direction || []).length ? (
                                  <p className="mt-1.5 text-xs text-slate-600">
                                    <span className="font-medium text-slate-500">
                                      预期改善：
                                    </span>
                                    {(ex.expected_direction || []).join("；")}
                                  </p>
                                ) : null}
                                {(ex.tradeoffs || []).length ? (
                                  <p className="mt-1 text-xs text-slate-600">
                                    <span className="font-medium text-slate-500">
                                      可能代价：
                                    </span>
                                    {(ex.tradeoffs || []).join("；")}
                                  </p>
                                ) : null}
                                {(ex.pass_criteria || []).length ? (
                                  <ul className="mt-2 list-inside list-disc text-xs text-slate-500">
                                    {(ex.pass_criteria || []).map((c, j) => (
                                      <li key={j}>{c}</li>
                                    ))}
                                  </ul>
                                ) : null}
                                <p className="mt-2 text-[10px] text-slate-400">
                                  须人工执行（manual_only）
                                </p>
                              </div>
                            </div>
                          </li>
                        );
                      })}
                    </ol>
                  </div>
                ) : null}
              </>
            ) : null}

            {data.disclaimer ? (
              <p className="text-center text-[11px] leading-relaxed text-slate-400">
                {data.disclaimer}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </>
  );

  if (isPanel) {
    return (
      <section className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
        {body}
      </section>
    );
  }

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-slate-900/45 p-4 backdrop-blur-[2px]">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-2xl">
        <div className="min-h-0 flex-1 overflow-y-auto">{body}</div>
      </div>
    </div>
  );
}

function FindingRow({
  finding,
  index,
  expanded,
  onToggle,
  renderEvidenceRefs,
}: {
  finding: BacktestInterpretFinding;
  index: number;
  expanded: boolean;
  onToggle: () => void;
  renderEvidenceRefs: (refs?: string[]) => ReactNode;
}) {
  const conf = confidenceLabel(finding.confidence);
  return (
    <li className="rounded-xl border border-slate-200 px-3.5 py-3">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-start gap-2 text-left"
      >
        <span className="mt-0.5 text-slate-400">
          {expanded ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${severityStyle(finding.severity)}`}
            >
              {severityLabel(finding.severity)}
            </span>
            {conf ? (
              <span className="rounded-full bg-slate-50 px-2 py-0.5 text-[10px] text-slate-500 ring-1 ring-inset ring-slate-200">
                {conf}
              </span>
            ) : null}
            <span className="font-semibold text-slate-900">
              {finding.title || finding.candidate_id || `诊断 ${index + 1}`}
            </span>
          </div>
          {finding.explanation ? (
            <p className="mt-1.5 text-sm leading-relaxed text-slate-600">
              {finding.explanation}
            </p>
          ) : null}
        </div>
      </button>
      {expanded ? (
        <div className="mt-3 border-t border-slate-100 pt-3 pl-6">
          <p className="mb-1.5 text-[11px] font-medium text-slate-400">
            关联证据
          </p>
          {renderEvidenceRefs(finding.evidence_refs)}
        </div>
      ) : null}
    </li>
  );
}
