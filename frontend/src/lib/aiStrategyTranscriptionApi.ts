/** AI 策略转写（聚宽 → SVQuant）：经本机 /api 转发 ResearchEngine。 */

import { authHeaders } from "./auth";

export type TranscriptionEngineMode = "auto" | "vectorized" | "event";
export type TranscriptionTargetEngine = "vectorized" | "event";
export type TranscriptionVerdict = "equivalent" | "degraded" | "blocked";
export type TranscriptionStatus = "ready" | "needs_input" | "report_only" | "rejected";
export type TranscriptionSeverity = "blocker" | "degraded" | "info";
export type TranscriptionImpact = "high" | "medium" | "low";

export type TranscriptionOption = {
  id: string;
  label: string;
  risk: TranscriptionImpact;
  note: string;
  recommended?: boolean;
};

export type TranscriptionIssue = {
  code: string;
  severity: TranscriptionSeverity;
  impact: TranscriptionImpact;
  line: number;
  title: string;
  why: string;
  effect: string;
  options: TranscriptionOption[];
  evidence: string;
  confidence: "certain" | "likely" | "needs_check";
  accepted?: boolean | null;
};

export type TranscriptionMapping = {
  jq: string;
  svq: string;
  status: "equivalent" | "degraded" | "blocked" | "config" | "needs_check";
  line: number;
  note?: string | null;
};

export type TranscriptionCheck = {
  id: "syntax" | "contract" | "security" | "future_data" | "fields";
  label: string;
  status: "pass" | "warn" | "fail" | "skipped";
  detail?: string | null;
  line?: number | null;
};

export type TranscribedStrategy = {
  strategy_name: string;
  strategy_code: string;
  description: string;
  used_fields: string[];
  assumptions: string[];
  warnings: string[];
};

export type StrategyTranscriptionResult = {
  transcription_id: string;
  status: TranscriptionStatus;
  verdict: TranscriptionVerdict;
  target_engine: TranscriptionTargetEngine;
  runnable: boolean;
  requires_ack: boolean;
  summary: string;
  issues: TranscriptionIssue[];
  mappings: TranscriptionMapping[];
  assumptions: string[];
  checks: TranscriptionCheck[];
  errors: string[];
  strategy: TranscribedStrategy | null;
  meta: {
    model_alias: string;
    prompt_version: string;
    capability_catalog_version: string;
    data_version: string;
    latency_ms: number;
  };
};

export type StrategyTranscriptionRequest = {
  code: string;
  context: {
    target: {
      engine_mode: TranscriptionEngineMode;
      universe?: string | null;
      benchmark?: string | null;
      start?: string | null;
      end?: string | null;
      initial_capital?: number | null;
    };
    accepted_degradations?: string[];
    report_only?: boolean;
    source_name?: string | null;
  };
  idempotency_key: string;
};

export async function ygTranscribeStrategy(
  body: StrategyTranscriptionRequest,
  signal?: AbortSignal,
): Promise<StrategyTranscriptionResult> {
  const res = await fetch("/api/ai/strategy-transcriptions", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
    signal,
  });
  const text = await res.text();
  let data: StrategyTranscriptionResult & { detail?: unknown; error?: string };
  try {
    data = JSON.parse(text) as typeof data;
  } catch {
    throw new Error(
      res.ok ? "响应不是 JSON" : `HTTP ${res.status}: ${text.slice(0, 200)}`,
    );
  }
  if (!res.ok) {
    if (res.status === 503) {
      throw new Error("AI 转写服务暂不可用（尚未配置或供应商异常）");
    }
    if (res.status === 504) {
      throw new Error("转写超时，请缩小代码范围或稍后重试");
    }
    if (res.status === 409) {
      throw new Error("幂等键冲突，请重新转写");
    }
    if (res.status === 422) {
      const detail = data.detail;
      const msg =
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail
                .map((d) =>
                  typeof d === "object" && d && "msg" in d
                    ? String((d as { msg: unknown }).msg)
                    : JSON.stringify(d),
                )
                .join("；")
            : data.error || "请求参数不符合约定";
      throw new Error(msg);
    }
    throw new Error(data.error || `HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return data;
}
