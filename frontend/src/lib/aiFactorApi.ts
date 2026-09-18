/** AI 因子草稿生成：经本机 /api 转发计算服务，浏览器不直连对方。 */

import { authHeaders } from "./auth";

export type AiFactorContext = {
  universe?: string | null;
  frequency?: "1d";
  allowed_library_names?: string[];
  preferred_factor_name?: string | null;
};

export type AiFactorDraft = {
  factor_name: string;
  factor_code: string;
  description: string;
  used_fields: string[];
  used_library_methods: string[];
  assumptions: string[];
  warnings: string[];
};

export type AiFactorGenerationResult = {
  generation_id: string;
  status: "ready" | "rejected";
  factor: AiFactorDraft | null;
  validation: {
    status: "passed" | "failed";
    capability_catalog_version?: string;
    errors: string[];
    warnings: string[];
  };
  meta?: {
    model_alias?: string;
    prompt_version?: string;
    latency_ms?: number;
  };
};

export type AiFactorGenerateRequest = {
  prompt: string;
  context?: AiFactorContext;
  idempotency_key: string;
};

export async function ygGenerateFactorDraft(
  body: AiFactorGenerateRequest,
  signal?: AbortSignal,
): Promise<AiFactorGenerationResult> {
  const res = await fetch("/api/ai/factor-generations", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      prompt: body.prompt,
      context: body.context || {},
      idempotency_key: body.idempotency_key,
    }),
    signal,
  });
  const text = await res.text();
  let data: AiFactorGenerationResult & { detail?: unknown; error?: string };
  try {
    data = JSON.parse(text) as typeof data;
  } catch {
    throw new Error(
      res.ok ? "响应不是 JSON" : `HTTP ${res.status}: ${text.slice(0, 200)}`,
    );
  }
  if (!res.ok) {
    if (res.status === 503) {
      throw new Error("AI 服务暂不可用（尚未配置或供应商异常）");
    }
    if (res.status === 504) {
      throw new Error("生成超时，请换个说法或稍后重试");
    }
    if (res.status === 409) {
      throw new Error("幂等键冲突，请重新生成");
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
