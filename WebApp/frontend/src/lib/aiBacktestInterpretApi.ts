/** AI 回测解读：经 /yg-api 调同事 RE，本机不存 Key。 */

import { newUuidV4 } from "./uuid";

export type BacktestInterpretType = "factor" | "strategy";
export type BacktestInterpretFocus =
  | "overall"
  | "risk"
  | "robustness"
  | "factor"
  | "execution";

export type BacktestInterpretRunContext = {
  validation_scheme?: string;
  commission_rate?: number | null;
  stamp_tax?: number | null;
  slippage_rate?: number | null;
};

export type BacktestInterpretEvidenceItem = {
  evidence_id: string;
  category?: string;
  value?: unknown;
  unit?: string | null;
  status?: string;
  source_paths?: string[];
  limitations?: string[];
};

export type BacktestInterpretFinding = {
  finding_id?: string;
  candidate_id?: string;
  severity?: string;
  title?: string;
  explanation?: string;
  evidence_refs?: string[];
  confidence?: string;
  limitations?: string[];
};

export type BacktestInterpretExperiment = {
  experiment_id?: string;
  priority?: number;
  hypothesis?: string;
  primary_variable?: string;
  expected_direction?: string[];
  tradeoffs?: string[];
  validation_method?: string;
  pass_criteria?: string[];
  evidence_refs?: string[];
  manual_only?: boolean;
};

export type BacktestInterpretationResult = {
  interpretation_id?: string;
  status: "ready" | "insufficient" | "rejected";
  mode?: string;
  evidence?: {
    schema_version?: string;
    result_fingerprint?: string;
    coverage?: string;
    warnings?: string[];
    items?: BacktestInterpretEvidenceItem[];
  };
  interpretation?: {
    summary?: string;
    findings?: BacktestInterpretFinding[];
    experiments?: BacktestInterpretExperiment[];
  } | null;
  disclaimer?: string;
  meta?: {
    model_alias?: string;
    prompt_version?: string;
    diagnostic_catalog_version?: string;
    latency_ms?: number;
  };
  detail?: unknown;
  error?: string;
};

export type BacktestInterpretRequest = {
  backtest_type: BacktestInterpretType;
  result: Record<string, unknown>;
  run_context?: BacktestInterpretRunContext;
  focus?: BacktestInterpretFocus;
  question?: string | null;
  idempotency_key: string;
};

export async function ygInterpretBacktest(
  body: BacktestInterpretRequest,
  signal?: AbortSignal,
): Promise<BacktestInterpretationResult> {
  const res = await fetch("/yg-api/api/ai/backtest-interpretations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      backtest_type: body.backtest_type,
      result: body.result,
      run_context: body.run_context || {},
      focus: body.focus || "overall",
      question: body.question ?? null,
      idempotency_key: body.idempotency_key,
    }),
    signal,
  });
  const text = await res.text();
  let data: BacktestInterpretationResult;
  try {
    data = JSON.parse(text) as BacktestInterpretationResult;
  } catch {
    throw new Error(
      res.ok ? "响应不是 JSON" : `HTTP ${res.status}: ${text.slice(0, 300)}`,
    );
  }
  if (!res.ok) {
    if (res.status === 503) {
      throw new Error("AI 解读服务暂不可用（开关关闭或维护中）");
    }
    if (res.status === 409) {
      throw new Error("幂等键冲突，请重试");
    }
    if (res.status === 400) {
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : "净值点过多或请求不合法（HTTP 400）",
      );
    }
    if (res.status === 422) {
      const detail = data.detail;
      const msg =
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail
                .map((x) =>
                  x && typeof x === "object" && "msg" in x
                    ? String((x as { msg: unknown }).msg)
                    : JSON.stringify(x),
                )
                .join("; ")
            : data.error || "请求字段不符合契约（HTTP 422）";
      throw new Error(msg);
    }
    throw new Error(data.error || `HTTP ${res.status}`);
  }
  return data;
}

export function newInterpretIdempotencyKey(): string {
  return newUuidV4();
}

/** 证据告警码 → 用户可读说明（诚实诊断，不粉饰） */
export const EVIDENCE_WARNING_LABELS: Record<string, string> = {
  NO_OUT_OF_SAMPLE: "当前为样本内回测，未做样本外或 Walk-forward 验证",
  SAMPLE_TOO_SHORT: "有效净值样本偏短，结论稳定性有限",
  COST_ASSUMPTION_UNKNOWN: "交易成本假设不完整（佣金/印花税/滑点有缺失）",
  ZERO_COST_ASSUMPTION: "策略有换手但成本假设为零，结果可能偏乐观",
  HIGH_TURNOVER: "换手偏高，需核对成本与可执行性",
  DEEP_DRAWDOWN: "回撤较深，需优先评估风险承受",
  WEAK_FACTOR_SIGNAL: "因子截面预测力偏弱（|IC| 较低）",
  INSUFFICIENT: "有效净值点不足，无法完整解读",
};

export function formatEvidenceWarning(code: string): string {
  return EVIDENCE_WARNING_LABELS[code] || code;
}

export function formatCoverageLabel(coverage?: string): string | null {
  if (!coverage) return null;
  if (coverage === "partial") return "证据覆盖：部分";
  if (coverage === "insufficient") return "证据覆盖：不足";
  if (coverage === "full" || coverage === "complete") return "证据覆盖：完整";
  return `证据覆盖：${coverage}`;
}

export function formatModeLabel(mode?: string): {
  short: string;
  detail: string;
} {
  if (mode === "llm_grounded") {
    return {
      short: "AI 排序",
      detail: "",
    };
  }
  if (mode === "deterministic_fallback") {
    return {
      short: "规则诊断",
      detail: "",
    };
  }
  if (mode === "not_applicable") {
    return { short: "不适用", detail: "" };
  }
  return { short: mode || "未知模式", detail: "" };
}

export function formatExperimentClipboard(
  ex: BacktestInterpretExperiment,
  index: number,
): string {
  const lines = [
    `【实验建议 #${ex.priority ?? index + 1}】`,
    ex.hypothesis || ex.experiment_id || "",
  ];
  if (ex.primary_variable) lines.push(`主变量：${ex.primary_variable}`);
  if (ex.validation_method) lines.push(`验证方法：${ex.validation_method}`);
  if ((ex.expected_direction || []).length) {
    lines.push(`预期改善：${(ex.expected_direction || []).join("；")}`);
  }
  if ((ex.tradeoffs || []).length) {
    lines.push(`可能代价：${(ex.tradeoffs || []).join("；")}`);
  }
  if ((ex.pass_criteria || []).length) {
    lines.push(`通过条件：${(ex.pass_criteria || []).join("；")}`);
  }
  lines.push("（须人工执行，不可自动改代码/重跑/下单）");
  return lines.filter(Boolean).join("\n");
}
